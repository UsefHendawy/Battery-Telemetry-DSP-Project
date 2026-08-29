#include <WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <math.h>
#include <arduinoFFT.h>

#define FFT_SAMPLES 64
#define FFT_SAMPLING_FREQ 100.0
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1

TwoWire I2C_Bus0 = TwoWire(0); 
TwoWire I2C_Bus1 = TwoWire(1); 

Adafruit_SSD1306 display1(SCREEN_WIDTH, SCREEN_HEIGHT, &I2C_Bus0, OLED_RESET);
Adafruit_SSD1306 display2(SCREEN_WIDTH, SCREEN_HEIGHT, &I2C_Bus0, OLED_RESET);
Adafruit_SSD1306 display3(SCREEN_WIDTH, SCREEN_HEIGHT, &I2C_Bus1, OLED_RESET);

double vReal[FFT_SAMPLES];
double vImag[FFT_SAMPLES];
ArduinoFFT<double> FFT = ArduinoFFT<double>(vReal,vImag, FFT_SAMPLES, FFT_SAMPLING_FREQ);

const int ADC_CH1_PIN = 34;
const int ADC_CH2_PIN = 35;
const int BTN_SCROLL  = 25; 
const int BTN_SELECT  = 27; 

const char *ssid = "ESP32_Telemetry_Node";
const char *password = "battery123";

WiFiUDP udp;
const IPAddress remoteIP(192, 168, 4, 2);
const unsigned int remotePort = 5005;

const int DSP_SAMPLES = 64;
float wave_buffer[SCREEN_WIDTH];
int wave_head = 0;

struct BatteryProfile {
  const char* name;
  const char* tag;
  float v_min;
  float v_max;
  bool use_high_lane;
};

const BatteryProfile profiles[] = {
  {"AA Alkaline",     "AA_ALK",     1.0, 1.6, false},
  {"AAA Alkaline",    "AAA_ALK",    1.0, 1.6, false},
  {"1.5V Zinc-Carbon","1.5V_ZINC",  1.0, 1.6, false},
  {"Li-Ion Pouch",    "LI_ION",     3.2, 4.2, false},
  {"9V Heavy Duty",   "9V_BATT",    7.0, 9.6, true},
  {"Supercapacitor",  "SUPERCAP",   0.0, 9.6, true}
};
const int total_profiles = 6;

int current_index = 0;
bool profile_locked = false;
unsigned long last_btn_time = 0;
unsigned long last_screen_update = 0;

float filtered_v = 0.0;
float filtered_soc = 0.0;

// Local DSP vars for the OLEDs
float dsp_rms = 0.0;
float dsp_p2p = 0.0;
float dsp_kurt = 3.0;
float dsp_cent = 10.0;
float dsp_flat = 0.02;

float read_oversampled_voltage(int pin, float multiplier) {
  long sum = 0;
  for (int i = 0; i < 64; i++) {
    sum += analogRead(pin);
    delayMicroseconds(50);
  }
  return (((float)sum / 64.0f * 3.3f) / 4095.0f) * multiplier;
}

// Note: computing metrics locally for the OLED HUD. PC dashboard computes its own.
void compute_dsp_metrics(int active_pin, float multiplier) {
  float samples[DSP_SAMPLES];
  float sum = 0.0, sum_sq = 0.0;
  float min_v = 999.0, max_v = -999.0;

  for (int i = 0; i < DSP_SAMPLES; i++) {
    int raw = analogRead(active_pin);
    float v = ((raw * 3.3f) / 4095.0f) * multiplier;
    samples[i] = v;
    sum += v;
    sum_sq += (v * v);
    if (v < min_v) min_v = v;
    if (v > max_v) max_v = v;
    delayMicroseconds(80);
  }
  dsp_p2p = max_v - min_v;

  float mean = sum / DSP_SAMPLES;
  float raw_rms = sqrt(sum_sq / DSP_SAMPLES);

  // IIR filter (tweak weights if display is too jittery)
  dsp_rms = (0.10f * raw_rms) + (0.90f * dsp_rms);

  float variance = 0.0;
  for (int i = 0; i < DSP_SAMPLES; i++) {
    variance += pow(samples[i] - mean, 2);
  }
  variance /= DSP_SAMPLES;
  
  float m4 = 0.0;
  for (int i = 0; i < DSP_SAMPLES; i++) {
    m4 += pow(samples[i] - mean, 4);
  }
  // Added 1e-6 to prevent division by zero
  float raw_kurt = (m4 / DSP_SAMPLES) / (pow(variance, 2) + 1e-6);
  if (raw_kurt > 15.0) raw_kurt = 15.0;
  
  dsp_kurt = (0.08f * raw_kurt) + (0.92f * dsp_kurt);

  // Hack: using p2p as a cheap proxy for spectral shape here to save CPU cycles.
  // The PC script handles the actual FFT math for these.
  float raw_centroid = 10.0 + (dsp_p2p * 120.0);
  if (raw_centroid > 50.0) raw_centroid = 50.0;
  dsp_cent = (0.10f * raw_centroid) + (0.90f * dsp_cent);

  float raw_flatness = 0.02 + (dsp_p2p * 0.4);
  if (raw_flatness > 0.99) raw_flatness = 0.99;
  dsp_flat = (0.10f * raw_flatness) + (0.90f * dsp_flat);
}

void drawScreen1_FFT() {
  double mean_v = 0.0;
  for (int i = 0; i < FFT_SAMPLES; i++) {
    mean_v += wave_buffer[i];
  }
  mean_v /= FFT_SAMPLES;

  for (int i = 0; i < FFT_SAMPLES; i++) {
    vReal[i] = (double)wave_buffer[i] - mean_v; 
    vImag[i] = 0.0;
  }

  FFT.windowing(FFT_WIN_TYP_HAMMING, FFT_FORWARD);
  FFT.compute(FFT_FORWARD);
  FFT.complexToMagnitude();

  double max_mag = 0.001;
  for (int i = 1; i < (FFT_SAMPLES / 2); i++) {
    if (vReal[i] > max_mag) {
      max_mag = vReal[i];
    }
  }

  display1.setCursor(0, 0);
  display1.println(" [ FFT ] ");

  const int NUM_BARS = 16;
  const int BAR_WIDTH = 6;
  const int BAR_GAP = 2;
  const int CHART_BOTTOM = 54;
  const int MAX_BAR_HEIGHT = 42;

  for (int b = 0; b < NUM_BARS; b++) {
    double bin_mag = (vReal[(b * 2) + 1] + vReal[(b * 2) + 2]) / 2.0;
    
    int bar_height = (int)((bin_mag / max_mag) * MAX_BAR_HEIGHT);
    if (bar_height > MAX_BAR_HEIGHT) bar_height = MAX_BAR_HEIGHT;
    if (bar_height < 1) bar_height = 1;

    int x = b * (BAR_WIDTH + BAR_GAP);
    int y = CHART_BOTTOM - bar_height;

    display1.fillRect(x, y, BAR_WIDTH, bar_height, SSD1306_WHITE);
  }

  display1.drawFastHLine(0, CHART_BOTTOM + 1, 128, SSD1306_WHITE);
  display1.setCursor(0, 56);
  display1.print("0Hz");
  display1.setCursor(50, 56);
  display1.print("25Hz");
  display1.setCursor(98, 56);
  display1.print("50Hz");
}

void setup() {
  Serial.begin(115200);

  pinMode(BTN_SCROLL, INPUT_PULLUP);
  pinMode(BTN_SELECT, INPUT_PULLUP);

  for (int i = 0; i < SCREEN_WIDTH; i++) wave_buffer[i] = 32.0;

  WiFi.softAP(ssid, password);
  udp.begin(remotePort);

  I2C_Bus0.begin(21, 22, 400000);
  display1.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  display2.begin(SSD1306_SWITCHCAPVCC, 0x3D);

  I2C_Bus1.begin(33, 32, 400000);
  display3.begin(SSD1306_SWITCHCAPVCC, 0x3C);
}

void loop() {
  bool scroll_pressed = (digitalRead(BTN_SCROLL) == LOW);
  bool select_pressed = (digitalRead(BTN_SELECT) == LOW);

  if (millis() - last_btn_time > 180) {
    if (scroll_pressed) {
      current_index = (current_index - 1 + total_profiles) % total_profiles;
      profile_locked = false;
      last_btn_time = millis();
    } else if (select_pressed) {
      profile_locked = !profile_locked;
      last_btn_time = millis();
    }
  }

  BatteryProfile active = profiles[current_index];

  int active_pin = active.use_high_lane ? ADC_CH2_PIN : ADC_CH1_PIN;
  float multiplier = active.use_high_lane ? 3.2f : 2.0f;
  
  compute_dsp_metrics(active_pin, multiplier);

  float raw_measured_v = read_oversampled_voltage(active_pin, multiplier);

  if (filtered_v == 0.0) filtered_v = raw_measured_v;
  filtered_v = (0.10f * raw_measured_v) + (0.90f * filtered_v);

  float target_soc = ((filtered_v - active.v_min) / (active.v_max - active.v_min)) * 100.0f;
  if (target_soc < 0.0f) target_soc = 0.0f;
  if (target_soc > 100.0f) target_soc = 100.0f;

  if (filtered_soc == 0.0) filtered_soc = target_soc;
  filtered_soc = (0.12f * target_soc) + (0.88f * filtered_soc);

  float normalized_y = 60.0f - ((filtered_v / active.v_max) * 45.0f);
  if (normalized_y < 15.0f) normalized_y = 15.0f;
  if (normalized_y > 62.0f) normalized_y = 62.0f;
  wave_buffer[wave_head] = normalized_y;
  wave_head = (wave_head + 1) % SCREEN_WIDTH;

  if (profile_locked) {
    int raw1 = analogRead(ADC_CH1_PIN);
    int raw2 = analogRead(ADC_CH2_PIN);
    
    // TODO: switch to snprintf if String() class causes heap fragmentation over time
    String packet = String(active.tag) + "," + String(raw1) + "," + String(raw2) + "," + String(filtered_soc, 1);
    
    Serial.println(packet);
    udp.beginPacket(remoteIP, remotePort);
    udp.print(packet);
    udp.endPacket();
  }

  if (millis() - last_screen_update > 100) {
    last_screen_update = millis();

    // SCREEN 1
    display1.clearDisplay();
    display1.setTextSize(1);
    display1.setTextColor(SSD1306_WHITE);

    if (!profile_locked) {
      display1.setCursor(0, 0);
      display1.println("[ PROFILE ]");
      display1.drawFastHLine(0, 12, 128, SSD1306_WHITE);
      display1.setCursor(0, 24);
      display1.print("> ");
      display1.println(active.name);
    } else {
      drawScreen1_FFT();
    }
    display1.display();

    // SCREEN 2
    display2.clearDisplay();
    display2.setTextSize(1);
    display2.setTextColor(SSD1306_WHITE);
    display2.setCursor(0, 0);
    display2.println("[ STATUS ]");
    display2.drawFastHLine(0, 12, 128, SSD1306_WHITE);
    display2.setCursor(0, 18);
    display2.print("VOLTS: ");
    display2.print(filtered_v, 2);
    display2.println(" V");
    display2.setCursor(0, 30);
    display2.print("SOC:   ");
    display2.print(filtered_soc, 1);
    display2.println(" %");

    display2.drawRect(0, 46, 128, 14, SSD1306_WHITE);
    int bar_width = (int)((filtered_soc / 100.0f) * 124.0f);
    if (bar_width > 0) {
      display2.fillRect(2, 48, bar_width, 10, SSD1306_WHITE);
    }
    display2.display();

    // SCREEN 3 
    display3.clearDisplay();
    display3.setTextSize(1);
    display3.setTextColor(SSD1306_WHITE);
    display3.setCursor(0, 0);
    display3.println("[ METRICS ]");
    display3.drawFastHLine(0, 12, 128, SSD1306_WHITE);

    display3.setCursor(0, 18);
    display3.print("RMS:  ");
    display3.print(dsp_rms, 2);
    display3.print(" V");

    display3.setCursor(0, 30);
    display3.print("KURT: ");
    display3.print(dsp_kurt, 2);

    display3.setCursor(0, 42);
    display3.print("CENT: ");
    display3.print(dsp_cent, 1);
    display3.print(" Hz");

    display3.setCursor(0, 54);
    display3.print("FLAT: ");
    display3.print(dsp_flat, 3);
    
    display3.display();
  }
  delay(15);
}