import serial
import time
import collections
import joblib
import warnings
import numpy as np
import pandas as pd
from scipy import signal
from scipy.fft import rfft, rfftfreq
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# Suppress scikit-learn feature name warnings for clean terminal output
warnings.filterwarnings("ignore")

# ==============================================================================
# --- SYSTEM CONFIGURATION ---
# ==============================================================================
SERIAL_PORT = 'COM3'     # Ensure this matches your active ESP32 COM port
BAUD_RATE = 115200
SAMPLING_FREQ = 100
MAX_SAMPLES = 200
MODEL_FILE = "battery_model.pkl"

FEATURE_NAMES = ["rms", "kurtosis", "spectral_centroid", "spectral_flatness", "peak_to_peak"]

# Load trained AI Model
try:
    ai_model = joblib.load(MODEL_FILE)
    print(f"🟩 AI Model Loaded Successfully from {MODEL_FILE}")
except Exception as e:
    print(f"🛑 Failed to load AI model file: {e}")
    exit()

# Open Serial Hardware Link
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
    time.sleep(2)
except Exception as e:
    print(f"🛑 HARDWARE LINK ERROR on {SERIAL_PORT}: {e}")
    exit()

ch1_buffer = collections.deque([3.6]*MAX_SAMPLES, maxlen=MAX_SAMPLES)
ch2_buffer = collections.deque([0.0]*MAX_SAMPLES, maxlen=MAX_SAMPLES)

plt.style.use('dark_background')
fig, (ax_time, ax_freq) = plt.subplots(2, 1, figsize=(11, 7))
fig.suptitle("🤖 AI-POWERED SMART BATTERY TELEMETRY HUD", fontsize=14, fontweight='bold', color='cyan')

line_ch1, = ax_time.plot([], [], label='CH1 (Low Volts / Pouch)', color='#00FFCC', lw=1.5)
line_ch2, = ax_time.plot([], [], label='CH2 (High Volts / 9V)', color='#FF3366', lw=1.5)
ax_time.set_ylabel("Voltage (V)")
ax_time.set_ylim(0, 11)
ax_time.grid(True, alpha=0.3)
ax_time.legend(loc='upper right')

line_fft, = ax_freq.plot([], [], color='#FFCC00', lw=1.5)
ax_freq.set_xlabel("Frequency (Hz)")
ax_freq.set_ylabel("Spectrum Power")
ax_freq.set_xlim(0, 50)
ax_freq.set_ylim(0, 0.5)
ax_freq.grid(True, alpha=0.3)

hud_text = fig.text(0.05, 0.91, "AI EVALUATING SIGNAL...", fontsize=10, fontweight='bold',
                    bbox=dict(boxstyle="round,pad=0.5", facecolor="#111122", edgecolor="cyan"))

# ==============================================================================
# --- MATH HELPERS FOR SOC & SOH ---
# ==============================================================================
def calculate_soc(label, volts):
    """Calculates State of Charge % based on current voltage and battery chemistry."""
    if "9V" in label:
        v_min, v_max = 6.0, 9.6
    elif "PRISMATIC" in label or "POUCH" in label or "LI_" in label:
        v_min, v_max = 3.2, 4.2
    elif "TRIPLE_A" in label or "AA_" in label or "ALKALINE" in label:
        v_min, v_max = 1.0, 1.6
    else:
        v_min, v_max = 3.0, 4.2
    
    soc = ((volts - v_min) / (v_max - v_min)) * 100.0
    return max(0.0, min(100.0, soc))  # Clamp between 0% and 100%

def calculate_soh(label):
    """Maps AI prediction label to State of Health % tier."""
    if "HEALTHY" in label:
        return 100.0
    elif "AGED_SIM" in label or "AGED" in label:
        return 85.0
    elif "DEGRADED" in label or "DEAD" in label:
        return 60.0
    else:
        return 95.0

def extract_features(time_signal):
    rms = np.sqrt(np.mean(time_signal**2))
    mean = np.mean(time_signal)
    std = np.std(time_signal) if np.std(time_signal) > 0 else 0.001
    kurtosis = np.mean((time_signal - mean)**4) / (std**4)
    peak_to_peak = np.max(time_signal) - np.min(time_signal)
    
    ac_signal = time_signal - mean
    fft_mag = np.abs(rfft(ac_signal)) / len(time_signal)
    fft_freqs = rfftfreq(len(time_signal), d=1/SAMPLING_FREQ)
    
    sum_mag = np.sum(fft_mag)
    centroid = np.sum(fft_freqs * fft_mag) / sum_mag if sum_mag > 0 else 0.0
    
    geom_mean = np.exp(np.mean(np.log(fft_mag + 1e-10)))
    arith_mean = np.mean(fft_mag)
    flatness = geom_mean / arith_mean if arith_mean > 0 else 0.0
    
    return [rms, kurtosis, centroid, flatness, peak_to_peak], fft_freqs, fft_mag

def update_dashboard(frame):
    while ser.in_waiting > 0:
        try:
            line = ser.readline().decode('utf-8').strip()
            if "," in line:
                raw1, raw2 = line.split(",")
                v1 = ((int(raw1) * 3.3) / 4095.0) * 2.0
                v2 = ((int(raw2) * 3.3) / 4095.0) * 3.2
                ch1_buffer.append(v1)
                ch2_buffer.append(v2)
        except Exception:
            pass

    arr1 = signal.medfilt(np.array(ch1_buffer), kernel_size=5)
    arr2 = signal.medfilt(np.array(ch2_buffer), kernel_size=5)
    
    line_ch1.set_data(range(MAX_SAMPLES), arr1)
    line_ch2.set_data(range(MAX_SAMPLES), arr2)
    
    # Select active lane (GPIO 35 high-voltage lane if >5V, else GPIO 34 low-voltage lane)
    active_arr = arr2 if np.mean(arr2) > 5.0 else arr1
    features, freqs, mags = extract_features(active_arr)
    
    line_fft.set_data(freqs, mags)
    
    # Run Live AI Inference using a named DataFrame to eliminate Warnings
    features_df = pd.DataFrame([features], columns=FEATURE_NAMES)
    prediction = ai_model.predict(features_df)[0]
    probs = ai_model.predict_proba(features_df)
    confidence = np.max(probs) * 100
    
    mean_v = np.mean(active_arr)
    soc_val = calculate_soc(prediction, mean_v)
    soh_val = calculate_soh(prediction)
    
    hud_text.set_text(
        f"🤖 DETECTED: {prediction}\n"
        f"⚡ VOLTS: {mean_v:.2f}V  |  🔋 SOC: {soc_val:.1f}%  |  🔬 SOH: {soh_val:.1f}%  |  CONFIDENCE: {confidence:.1f}%"
    )
    
    return line_ch1, line_ch2, line_fft, hud_text

ani = animation.FuncAnimation(fig, update_dashboard, interval=50, blit=False)
plt.tight_layout(rect=[0, 0, 1, 0.93])
plt.show()

ser.close()