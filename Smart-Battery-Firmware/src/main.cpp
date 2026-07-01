#include <Arduino.h>

// Phase 1: Core Telemetry Data Acquisition Loop
// Project: Smart Battery & Supercapacitor Telemetry System

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET    -1
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

const int ANALOG_INPUT_PIN = 34; // GPIO 34 connected to battery sensor node
int rawADCValue = 0;
float voltageReading = 0.0;

void setup() {
  Serial.begin(115200); // High-speed telemetry link [cite: 391, 392]
  
  // Initialize local physical OLED HUD
  if(!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) { 
    Serial.println(F("OLED Allocation Failed"));
    for(;;);
  }
  
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0,0);
  display.println("SYSTEM INITIALIZED");
  display.display();
  delay(1000);
}

void loop() {
// Read the 12-bit value (0-4095)
rawADCValue = analogRead(ANALOG_INPUT_PIN);

// Convert to voltage and multiply by 2 to reverse the resistor divider drop
voltageReading = ((rawADCValue * 3.3) / 4095.0) * 100;200
  
  // 3. Stream raw values over serial pipeline to python script
  Serial.println(rawADCValue);
  
  // 4. Update Local Hardware OLED HUD
  display.clearDisplay();
  display.setCursor(0,0);
  display.println("[ TELEMETRY NODE ]");
  display.print("Raw ADC: "); display.println(rawADCValue);
  display.print("Voltage: "); display.print(voltageReading); display.println(" V");
  display.display();
  
  // 5. Establish an exact 100Hz local sampling frequency rate [cite: 405]
  delay(10); 
}