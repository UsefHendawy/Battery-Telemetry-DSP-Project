import serial
import time
import numpy as np
from scipy import signal
import matplotlib.pyplot as plt

# --- HARDWARE PORT CONFIGURATION ---
# IMPORTANT: Change 'COM3' to match your exact Device Manager port number!
SERIAL_PORT = 'COM3' 
BAUD_RATE = 115200

print(f"Opening Telemetry Data Pipe on {SERIAL_PORT}...")

try:
    # Initialize the physical USB serial bridge link
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2) # Give the ESP32 a brief moment to reset after connection
    print("Link Established! Streaming live voltage packets...")
    
    raw_data_packets = []
    
    # 1. Capture exactly 200 data points from the physical desk setup (2 seconds at 100Hz)
    while len(raw_data_packets) < 200:
        if ser.in_waiting > 0:
            # Read line from physical USB, strip hidden bits, convert to string
            packet_line = ser.readline().decode('utf-8').strip()
            
            # Defensive check: ensure the stream line is an integer
            if packet_line.isdigit():
                raw_data_packets.append(int(packet_line))
                print(f"Packet [{len(raw_data_packets)}/200] Recv: {packet_line}", end='\r')

    ser.close() # Safely close hardware port
    print("\nData window fully captured! Shutting down serial pipe.")
    
    # --- DSP SIGNAL PROCESSING PIPELINE ---
    # Convert raw list into a fast NumPy array vector
    raw_array = np.array(raw_data_packets)
    
    # Apply your verified SciPy median filter to strip electromagnetic static noise
    filtered_array = signal.medfilt(raw_array, kernel_size=5)
    
    # Render the Live Capture Comparison Plot
    plt.figure(figsize=(10, 5))
    plt.plot(raw_array, label="Raw Unfiltered Serial Stream (ADC Values)", color="crimson", alpha=0.5)
    plt.plot(filtered_array, label="Cleaned Signal (SciPy Median Filter)", color="darkturquoise", linewidth=2)
    plt.title("Smart Battery Telemetry - Live USB Hardware Data Capture")
    plt.xlabel("Sample Count")
    plt.ylabel("Raw Digital Amplitude (0 - 4095)")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.show()

except Exception as e:
    print(f"\n🛑 CRITICAL LINK ERROR: Could not read port {SERIAL_PORT}.")
    print(f"Reason: {e}")
    print("Fix: Verify your ESP32 is plugged in and change SERIAL_PORT on Line 8.")