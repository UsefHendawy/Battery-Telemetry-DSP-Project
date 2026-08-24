import serial
import time
import csv
import collections
import numpy as np
from scipy import signal
from scipy.fft import rfft, rfftfreq


SERIAL_PORT = 'COM3'  
BAUD_RATE = 115200    
SAMPLING_FREQ = 100   
MAX_SAMPLES = 200     
OUTPUT_DATABASE_FILE = "bp_log.csv"  




# --- MODE SELECTOR MATRIX ---
# TARGET_MODE options: "LOW_VOLTAGE_CELL" or "HIGH_VOLTAGE_BATTERY"
TARGET_MODE = "LOW_VOLTAGE_CELL" 

if TARGET_MODE == "HIGH_VOLTAGE_BATTERY":
    CURRENT_SOURCE_LABEL = "SUPER_CAPACITOR"
else:
    CURRENT_SOURCE_LABEL = "Triple_A_ZINC_CARBON_BATTERY"

# ==============================================================================




raw_buffer = collections.deque([3.6]*MAX_SAMPLES, maxlen=MAX_SAMPLES) 

print("="*80)
print(f" INITIALIZING BATTERY PROFILE HARVESTOR")
print(f" Target Profile Mode: {TARGET_MODE}")
print(f" Assigned Dataset Tag: {CURRENT_SOURCE_LABEL}")
print("="*80)

try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1) 
    time.sleep(2)
except Exception as e:
    print(f" HARDWARE LINK ERROR: Could not open port {SERIAL_PORT}.\nReason: {e}")
    exit()

try:
    with open(OUTPUT_DATABASE_FILE, mode='x', newline='') as f:
        writer = csv.writer(f)

        writer.writerow(["rms", "kurtosis", "spectral_centroid", "spectral_flatness", "peak_to_peak", "label"])
    print(f" Fresh database sheet constructed successfully: {OUTPUT_DATABASE_FILE}")
except FileExistsError:
    print(f" Existing sheet identified. Appending rows to current file: {OUTPUT_DATABASE_FILE}")


def extract_signal_features(time_signal):
    """
    Applies statistical equations over a continuous signal window array block
    to generate a clean 5-dimensional descriptive feature vector.
    """
    rms = np.sqrt(np.mean(time_signal**2))

# kurtosis calculations 
    mean = np.mean(time_signal)
    std = np.std(time_signal) if np.std(time_signal) > 0 else 0.001
    kurtosis = np.mean((time_signal - mean)**4) / (std**4)
    
    # Peak-to-Peak
    peak_to_peak = np.max(time_signal) - np.min(time_signal)
    
    # frequency domain spectral data 
    ac_signal = time_signal - mean 
    fft_mag = np.abs(rfft(ac_signal)) / len(time_signal)
    fft_freqs = rfftfreq(len(time_signal), d=1/SAMPLING_FREQ)
    
    # Spectral Centroid
    sum_mag = np.sum(fft_mag)
    spectral_centroid = np.sum(fft_freqs * fft_mag) / sum_mag if sum_mag > 0 else 0.0
    
    # Spectral Flatness 
    geom_mean = np.exp(np.mean(np.log(fft_mag + 1e-10)))
    arith_mean = np.mean(fft_mag)
    spectral_flatness = geom_mean / arith_mean if arith_mean > 0 else 0.0
    
    return [rms, kurtosis, spectral_centroid, spectral_flatness, peak_to_peak]

print("\n Data acquisition highway active, harvesting telemetry snapshots...")
print(" Press CTRL+C at any time to pause logging and save database safely.\n")

records_logged = 0
try:
    while True:
        samples_collected = 0

        while samples_collected < MAX_SAMPLES:
            if ser.in_waiting > 0:
                try:
                    packet_line = ser.readline().decode('utf-8').strip()
                    
                    if "," in packet_line:
                        low_str, high_str = packet_line.split(",")
                        
                        if TARGET_MODE == "LOW_VOLTAGE_CELL" and low_str.isdigit():
                            raw_adc = int(low_str)
                            true_voltage = ((raw_adc * 3.3) / 4095.0) * 2.0
                            
                        elif TARGET_MODE == "HIGH_VOLTAGE_BATTERY" and high_str.isdigit():
                            raw_adc = int(high_str)
                            true_voltage = ((raw_adc * 3.3) / 4095.0) * 3.2
                        else:
                            continue 
                            
                        raw_buffer.append(true_voltage) 
                        samples_collected += 1
                except Exception:
                    pass 
        
        filtered_array = signal.medfilt(np.array(raw_buffer), kernel_size=5) 
        
        features = extract_signal_features(filtered_array)
        
        with open(OUTPUT_DATABASE_FILE, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(features + [CURRENT_SOURCE_LABEL])
            
        records_logged += 1
        print(f" Row Vector Logged: [{records_logged}] | Voltage Sample: {true_voltage:.2f}V | Centroid: {features[2]:.2f} Hz | RMS: {features[0]:.3f}V", end='\r')
        
        time.sleep(2)

except KeyboardInterrupt:
    print("\n\n🛑 Ingestion halted by user gesture. Parking serial data pipelines...")
finally:
    ser.close() 
    print(f"Data saved. Recorded {records_logged} feature vectors inside database: {OUTPUT_DATABASE_FILE}.")
    print("="*80)