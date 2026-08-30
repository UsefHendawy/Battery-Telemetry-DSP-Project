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
LOG_FILE = "bp_log.csv"  

#--------------------------------------------------------------------------------
# ---------------------------------- SELECTOR -----------------------------------

TARGET_MODE = "CELL" 

if TARGET_MODE == "BATTERY":
    SOURCE_LABEL = "SUPERCAP"
else:
    SOURCE_LABEL = "AAA_ZINC"

#--------------------------------------------------------------------------------
#--------------------------------------------------------------------------------

raw_buffer = collections.deque([3.6]*MAX_SAMPLES, maxlen=MAX_SAMPLES) 

print("Starting battery profile logger...")
print(f"Mode: {TARGET_MODE} | Label: {SOURCE_LABEL}")

try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1) 
    time.sleep(2)
except serial.SerialException as err:
    print(f"Error opening port {SERIAL_PORT}: {err}")
    exit()

try:
    with open(LOG_FILE, mode='x', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["rms", "kurtosis", "spectral_centroid", "spectral_flatness", "peak_to_peak", "label"])
    print(f"Created new log file: {LOG_FILE}")
except FileExistsError:
    print(f"Found existing file, appending to {LOG_FILE}")

def get_features(signal_arr):
    """Calculates RMS, kurtosis, centroid, flatness, and P2P from the voltage buffer."""
    rms = np.sqrt(np.mean(signal_arr**2))
    mean = np.mean(signal_arr)
    
    std = np.std(signal_arr) + 1e-6
    kurtosis = np.mean((signal_arr - mean)**4) / (std**4)
    
    p2p = np.max(signal_arr) - np.min(signal_arr)
    
    ac_signal = signal_arr - mean 
    fft_mag = np.abs(rfft(ac_signal)) / len(signal_arr)
    fft_freqs = rfftfreq(len(signal_arr), d=1/SAMPLING_FREQ)
    
    sum_mag = np.sum(fft_mag) + 1e-10
    centroid = np.sum(fft_freqs * fft_mag) / sum_mag
    
    geom_mean = np.exp(np.mean(np.log(fft_mag + 1e-10)))
    arith_mean = np.mean(fft_mag) + 1e-10
    flatness = geom_mean / arith_mean
    
    return [rms, kurtosis, centroid, flatness, p2p]

print("\nLogging active. Press CTRL+C to stop.\n")

records_saved = 0
try:
    while True:
        samples = 0
        ser.reset_input_buffer() # Clear backlog so we get fresh samples
        
        while samples < MAX_SAMPLES:
            if ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8').strip()
                    if "," in line:
                        parts = line.split(",")
                        
                        if len(parts) >= 3: # Handle the 4 parts sent by ESP: tag, raw1, raw2, soc
                            low_str = parts[1]
                            high_str = parts[2]
                            
                            if TARGET_MODE == "CELL":
                                raw_adc = int(low_str)
                                true_v = ((raw_adc * 3.3) / 4095.0) * 2.0
                            else:
                                raw_adc = int(high_str)
                                true_v = ((raw_adc * 3.3) / 4095.0) * 3.2
                                
                            raw_buffer.append(true_v) 
                            samples += 1
                except ValueError:
                    pass
        
        filtered = signal.medfilt(np.array(raw_buffer), kernel_size=5) 
        features = get_features(filtered)
        
        with open(LOG_FILE, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(features + [SOURCE_LABEL])
            
        records_saved += 1
        print(f"Logged: [{records_saved}] | V: {np.mean(filtered):.2f} | Cent: {features[2]:.2f}Hz | RMS: {features[0]:.3f}V", end='\r')

except KeyboardInterrupt:
    print("\n\nStopped by user.")
finally:
    ser.close() 
    print(f"\nSaved {records_saved} rows to {LOG_FILE}.")