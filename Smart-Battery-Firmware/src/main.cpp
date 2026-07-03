#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// --- DISPLAY CONFIGURATION ---
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET    -1  // Shared reset pin
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// --- PHYSICAL HARDWARE PIN CONFIGURATION ---
const int PIN_LOW_VOLTAGE  = 34; // Channel 1: 10k/10k low-voltage lane
const int PIN_HIGH_VOLTAGE = 35; // Channel 2: 22k/10k high-voltage lane

void setup() {
  // Initialize high-speed USB data pipeline matching Python telemetry settings
  Serial.begin(115200);
  
  // Configure both internal hardware gates as analog input reception lanes
  pinMode(PIN_LOW_VOLTAGE, INPUT);
  pinMode(PIN_HIGH_VOLTAGE, INPUT);

  // Initialize the local I2C OLED display on standard ESP32 pins (SDA=21, SCL=22)
  if(!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) { 
    Serial.println("OLED Allocation Failed");
    for(;;); // Freeze if hardware is missing to prevent silent code failures
  }
  
  // Clear buffer and show a sharp boot splash screen
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(15, 20);
  display.println("Smart Telemetry Node");
  display.setCursor(25, 35);
  display.println("Initializing...");
  display.display();
  delay(1500); 
}

void loop() {
  // 1. Read raw 12-bit digital integers (0 - 4095) directly from silicon gates
  int rawLowVolt   = analogRead(PIN_LOW_VOLTAGE);
  int rawHighVolt  = analogRead(PIN_HIGH_VOLTAGE);
  
  // 2. Local Edge Calibration Math
  // We compute local representations purely to print out on the physical screen hud
  float vLowCalc  = ((rawLowVolt * 3.3) / 4095.0) * 2.0;  // Reverse 10k/10k hardware split
  float vHighCalc = ((rawHighVolt * 3.3) / 4095.0) * 3.2; // Reverse 22k/10k hardware split

  // 3. DRAW DYNAMIC OLED DIAGNOSTIC HUD
  display.clearDisplay();
  
  // Header Banner
  display.setTextSize(1);
  display.setCursor(16, 0);
  display.println("[ TELEMETRY HUD ]");
  display.drawFastHLine(0, 10, SCREEN_WIDTH, SSD1306_WHITE); // Fixed function name!

  // Channel 1 Readout (GPIO 34)
  display.setCursor(0, 18);
  display.print("CH1 (34) Pouch: ");
  display.print(vLowCalc, 2);
  display.println(" V");

  // Channel 2 Readout (GPIO 35)
  display.setCursor(0, 34);
  display.print("CH2 (35) 9V   : ");
  display.print(vHighCalc, 2);
  display.println(" V");
  
  // System Status Info Block
  display.drawFastHLine(0, 50, SCREEN_WIDTH, SSD1306_WHITE); // Fixed function name!
  display.setCursor(0, 54);
  display.print("Sampling Rate: 100 Hz");
  
  // Push the memory frame buffer straight to the physical pixels
  display.display();

  // 4. MULTI-CHANNEL PACKET TRANSMISSION
  // Send both raw sensor channels split by a clear comma delimiter: "LOW,HIGH"
  Serial.print(rawLowVolt);
  Serial.print(",");
  Serial.println(rawHighVolt);
  
  // Establish rigid 100Hz sampling frequency (Pause 10ms between loops)
  delay(10); 
}