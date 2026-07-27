import serial
import time
import csv
import collections
import numpy as np
from scipy import signal
from scipy.fft import rfft, rfftfreq

# ==============================================================================
# --- SYSTEM CONTROL & PARAMETERS ---
# ==============================================================================
SERIAL_PORT = 'COM3'  # Ensure this matches your Device Manager COM port!
BAUD_RATE = 115200    # High-speed data pipe matching firmware
SAMPLING_FREQ = 100   # Sampling rate of ~100Hz (10ms delays)
MAX_SAMPLES = 200     # Window frame slice size (2 seconds of data)
OUTPUT_DATABASE_FILE = "telemetry_features_db.csv"  # Target dataset file

# --- MODE SELECTOR MATRIX ---
# TARGET_MODE options: "LOW_VOLTAGE_CELL" or "HIGH_VOLTAGE_BATTERY"
TARGET_MODE = "LOW_VOLTAGE_CELL" 

if TARGET_MODE == "HIGH_VOLTAGE_BATTERY":
    CURRENT_SOURCE_LABEL = "9V_ALKALINE_BATTERY_HEALTHY"
else:
    CURRENT_SOURCE_LABEL = "COIN_BATTERY_HEALTHY"

# ==============================================================================
# --- LOCAL STORAGE INITIALIZATION ---
# ==============================================================================
raw_buffer = collections.deque([3.6]*MAX_SAMPLES, maxlen=MAX_SAMPLES) # Rolling FIFO ring buffer

print("="*80)
print(f"📡 INITIALIZING STEP 4 FEATURE LOGGER ENGINE")
print(f"🔬 Target Profile Mode: {TARGET_MODE}")
print(f"🏷️  Assigned Dataset Tag: {CURRENT_SOURCE_LABEL}")
print("="*80)

# Establish connection to the hardware COM port
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1) # Open serial tunnel
    time.sleep(2) # Protective edge-node boot up delay
except Exception as e:
    print(f"🛑 HARDWARE LINK ERROR: Could not open port {SERIAL_PORT}.\nReason: {e}")
    exit()

# Setup local database sheet file structural headers
try:
    with open(OUTPUT_DATABASE_FILE, mode='x', newline='') as f:
        writer = csv.writer(f)
        # Write clean descriptive headers for the machine learning pipeline
        writer.writerow(["rms", "kurtosis", "spectral_centroid", "spectral_flatness", "peak_to_peak", "label"])
    print(f"🟩 Fresh database sheet constructed successfully: {OUTPUT_DATABASE_FILE}")
except FileExistsError:
    print(f"🟨 Existing sheet identified. Appending rows to current file: {OUTPUT_DATABASE_FILE}")

# ==============================================================================
# --- MATHEMATICAL FEATURE EXTRACTION CORE ---
# ==============================================================================
def extract_signal_features(time_signal):
    """
    Applies statistical equations over a continuous signal window array block
    to generate a clean 5-dimensional descriptive feature vector.
    """
    # 1. TIME-DOMAIN DESCRIPTIVE METRICS
    # Root Mean Square (RMS) -> Signals true overall power density
    rms = np.sqrt(np.mean(time_signal**2))
    
    # Kurtosis -> Evaluates wave shape "sharpness" and sudden variant spikes
    mean = np.mean(time_signal)
    std = np.std(time_signal) if np.std(time_signal) > 0 else 0.001
    kurtosis = np.mean((time_signal - mean)**4) / (std**4)
    
    # Peak-to-Peak -> Pinpoints absolute voltage limits and load drops
    peak_to_peak = np.max(time_signal) - np.min(time_signal)
    
    # 2. FREQUENCY-DOMAIN (FOURIER) SPECTRAL METRICS
    ac_signal = time_signal - mean # Remove DC baseline shift component
    fft_mag = np.abs(rfft(ac_signal)) / len(time_signal) # Calculate Fast Fourier Transform
    fft_freqs = rfftfreq(len(time_signal), d=1/SAMPLING_FREQ)
    
    # Spectral Centroid -> Determines the active frequency center of mass
    sum_mag = np.sum(fft_mag)
    spectral_centroid = np.sum(fft_freqs * fft_mag) / sum_mag if sum_mag > 0 else 0.0
    
    # Spectral Flatness -> Measures if signal carries structured tone or random EMI static
    geom_mean = np.exp(np.mean(np.log(fft_mag + 1e-10)))
    arith_mean = np.mean(fft_mag)
    spectral_flatness = geom_mean / arith_mean if arith_mean > 0 else 0.0
    
    return [rms, kurtosis, spectral_centroid, spectral_flatness, peak_to_peak]

# ==============================================================================
# --- RUNTIME DATA ACQUISITION INGESTION ENGINE ---
# ==============================================================================
print("\n🚀 Data acquisition highway active! Harvesting telemetry snapshots...")
print("💡 Press CTRL+C at any time to pause logging and save database safely.\n")

records_logged = 0
try:
    while True:
        samples_collected = 0
        # Ingest a clean full array slice window from the serial bus queue
        # Ingest a clean full array slice window from the serial bus queue
        while samples_collected < MAX_SAMPLES:
            if ser.in_waiting > 0:
                try:
                    packet_line = ser.readline().decode('utf-8').strip()
                    
                    # Check if the incoming packet contains our dual-channel comma split
                    if "," in packet_line:
                        # Split the string into distinct low-voltage and high-voltage string tokens
                        low_str, high_str = packet_line.split(",")
                        
                        # SYSTEM ADAPTIVE PARSING MATRIX
                        if TARGET_MODE == "LOW_VOLTAGE_CELL" and low_str.isdigit():
                            raw_adc = int(low_str)
                            # Reverse standard 10k/10k hardware division (Multiply by 2.0)
                            true_voltage = ((raw_adc * 3.3) / 4095.0) * 2.0
                            
                        elif TARGET_MODE == "HIGH_VOLTAGE_BATTERY" and high_str.isdigit():
                            raw_adc = int(high_str)
                            # HIGH VOLTAGE 9V MODE: Reverse 22k/10k series divider split (Multiply by 3.2)
                            true_voltage = ((raw_adc * 3.3) / 4095.0) * 3.2
                        else:
                            continue # Skip row if formatting mismatches
                            
                        raw_buffer.append(true_voltage) # Queue calibrated metric line
                        samples_collected += 1
                except Exception:
                    pass # Shield loop against garbled serial bits
        
        # Signal conditioning: Run full array vector frame slice through SciPy Median Filter [cite: 1265, 1266]
        filtered_array = signal.medfilt(np.array(raw_buffer), kernel_size=5) # Clean raw tracking static [cite: 1179, 1265, 1266]
        
        # Calculate mathematical feature maps
        features = extract_signal_features(filtered_array)
        
        # Commit the 5 features + target source label row straight into local spreadsheet
        with open(OUTPUT_DATABASE_FILE, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(features + [CURRENT_SOURCE_LABEL])
            
        records_logged += 1
        # Clear line terminal tracker to track progress metrics clearly
        print(f"📝 Row Vector Logged: [{records_logged}] | Voltage Sample: {true_voltage:.2f}V | Centroid: {features[2]:.2f} Hz | RMS: {features[0]:.3f}V", end='\r')
        
        time.sleep(2) # Space out snapshots evenly to capture continuous real-time changes 

except KeyboardInterrupt:
    print("\n\n🛑 Ingestion halted by user gesture. Parking serial data pipelines...")
finally:
    ser.close() # Safely release ownership lock on physical device COM port [cite: 1272, 1273]
    print(f"🏁 System safely parked! Recorded {records_logged} feature vectors inside database: {OUTPUT_DATABASE_FILE}.")
    print("="*80)