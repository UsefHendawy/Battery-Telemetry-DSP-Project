// Firmware Baseline Environment Test Script
// Project: Cavitation Acoustic Telemetry System

int dummySignal = 0;
float timeStep = 0.0;

void setup() {
  // Initialize the high-speed serial communication line (115200 baud rate)
  Serial.begin(115200);
  while(!Serial) {
    ; // Wait for serial port to connect. Needed for native USB port only
  }
}

void loop() {
  // Generate a fake 10Hz acoustic cavitation wave using a sine function
  // We scale it by 512 and add 512 to center it on a standard 10-bit analog range (0-1023)
  dummySignal = (sin(timeStep) * 512) + 512;
  
  // Print the fake signal to the Serial monitor
  Serial.println(dummySignal);
  
  // Increment our time step slightly to keep the wave moving smoothly
  timeStep += 0.1;
  
  // Delay for 10 milliseconds to simulate a 100Hz analog sampling rate
  delay(10);
}