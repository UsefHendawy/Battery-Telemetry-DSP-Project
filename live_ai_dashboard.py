import socket
import collections
import time
import os
import csv
import warnings
import serial
import serial.tools.list_ports
import numpy as np
from scipy import signal
from scipy.fft import rfft, rfftfreq
import matplotlib.pyplot as plt
import matplotlib.animation as animation

warnings.filterwarnings("ignore")

# ==============================================================================
# --- SYSTEM CONFIGURATION ---
# ==============================================================================
BAUD_RATE = 115200
UDP_IP = "0.0.0.0"
UDP_PORT = 5005
SAMPLING_FREQ = 100
MAX_SAMPLES = 300
LOG_FILE = "telemetry_run_log.csv"

# Auto-Connect Link (Wired Serial or Wireless UDP)
ser = None
sock = None
connection_mode = "SEARCHING"

ports = [
    p.device for p in serial.tools.list_ports.comports()
    if any(k in p.description for k in ["CP210", "CH340", "USB", "Serial"]) or "COM" in p.device
]

for port in ports:
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=0.01)
        connection_mode = f"WIRED USB ({port})"
        print(f"🔌 Connected to ESP32 on {port}!")
        break
    except:
        ser = None

if ser is None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((UDP_IP, UDP_PORT))
        sock.setblocking(False)
        connection_mode = f"WIRELESS RF (UDP Port {UDP_PORT})"
        print(f"📡 Listening on Wireless UDP Port {UDP_PORT}...")
    except Exception as e:
        print(f"🛑 Port Error: {e}")
        exit()

# Buffers & Diagnostic State
ch1_buffer = collections.deque([0.0] * MAX_SAMPLES, maxlen=MAX_SAMPLES)
ch2_buffer = collections.deque([0.0] * MAX_SAMPLES, maxlen=MAX_SAMPLES)
voltage_history = collections.deque(maxlen=50) # For dV/dt calculation
current_profile_tag = "WAITING"
current_soc_from_esp = 0.0

start_time = time.time()
last_time_step = time.time()

# Ensure CSV Log file exists with full mathematical headers
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp", "profile", "voltage_v", "soc_pct", "soh_pct",
            "rms_v", "p2p_v", "dv_dt_mvs", "snr_db", "skewness", "kurtosis",
            "crest_factor", "centroid_hz", "flatness", "rolloff_hz"
        ])

# ==============================================================================
# --- DASHBOARD UI SETUP ---
# ==============================================================================
plt.style.use('dark_background')
fig, (ax_time, ax_freq) = plt.subplots(2, 1, figsize=(11, 8.0))
fig.suptitle(f"📡 PRECISION BATTERY TELEMETRY & DSP STATION | {connection_mode}", fontsize=12, fontweight='bold', color='cyan')

line_ch1, = ax_time.plot([], [], color='#00FFCC', lw=1.5, label="Lane 1 (CH1 Low-Volts)")
line_ch2, = ax_time.plot([], [], color='#FF3366', lw=1.5, label="Lane 2 (CH2 High-Volts)")
ax_time.set_ylabel("Voltage (V)")
ax_time.set_ylim(0, 11)
ax_time.grid(True, alpha=0.3)
ax_time.legend(loc="upper right")

line_fft, = ax_freq.plot([], [], color='#FFCC00', lw=1.5)
ax_freq.set_xlabel("Frequency (Hz)")
ax_freq.set_ylabel("Spectral Power Density")
ax_freq.set_xlim(0, 50)
ax_freq.grid(True, alpha=0.3)

hud_text = fig.text(0.02, 0.85, "WAITING FOR TELEMETRY...", fontsize=8.2, fontweight='bold', bbox=dict(facecolor="#111122", edgecolor="cyan"))

# ==============================================================================
# --- COMPREHENSIVE MATHEMATICAL & DSP SUITE ---
# ==============================================================================
def calculate_physics_soh(p2p, profile):
    """
    Deterministic State of Health (SOH) calculation based on 
    Internal Impedance & Transient Voltage Sag under circuit load.
    Only applicable to rechargeable chemistries (Li-Ion).
    """
    if "LI" not in profile:
        return None, "N/A (Primary Single-Use Cell)"
    
    # Baseline thresholds for 3.7V Li-Ion pouch cells under test
    V_p2p_fresh = 0.020    # 20mV ripple on a healthy, low-ESR cell
    V_p2p_degraded = 0.120 # 120mV ripple on an aged, high-ESR cell
    
    # Map impedance sag: SOH degrades from 100% down to 80% (EOL)
    soh = 100.0 - (((p2p - V_p2p_fresh) / (V_p2p_degraded - V_p2p_fresh)) * 20.0)
    soh = max(70.0, min(100.0, soh))
    
    if soh >= 92.0:
        health_status = "EXCELLENT / OPTIMAL RETENTION"
    elif soh >= 80.0:
        health_status = "NOMINAL / NORMAL AGING"
    else:
        health_status = "CRITICAL / RETIRED CELL (EOL)"
        
    return soh, health_status

def extract_full_metrics(time_signal, dt):
    mean_v = np.mean(time_signal)
    std_v = np.std(time_signal) if np.std(time_signal) > 0 else 0.0001

    # 1. Amplitude & Calculus Metrics
    rms = np.sqrt(np.mean(time_signal**2))
    p2p = np.max(time_signal) - np.min(time_signal)
    
    voltage_history.append((time.time(), mean_v))
    if len(voltage_history) >= 2:
        dv = voltage_history[-1][1] - voltage_history[0][1]
        dt_span = voltage_history[-1][0] - voltage_history[0][0]
        dv_dt = (dv / dt_span) * 1000.0 if dt_span > 0 else 0.0 # mV/s
    else:
        dv_dt = 0.0

    # 2. Signal Quality & Higher Statistical Moments
    snr_db = 20.0 * np.log10(max(mean_v / std_v, 1.0))
    skewness = np.mean(((time_signal - mean_v) / std_v)**3)
    kurtosis = np.mean(((time_signal - mean_v) / std_v)**4)
    crest_factor = (np.max(np.abs(time_signal - mean_v))) / (std_v)

    # 3. Frequency Domain Metrics (FFT)
    ac_signal = time_signal - mean_v
    fft_mag = np.abs(rfft(ac_signal)) / len(time_signal)
    fft_freqs = rfftfreq(len(time_signal), d=1/SAMPLING_FREQ)

    sum_mag = np.sum(fft_mag)
    centroid = np.sum(fft_freqs * fft_mag) / sum_mag if sum_mag > 0 else 0.0
    arith_mean = np.mean(fft_mag)
    flatness = np.exp(np.mean(np.log(fft_mag + 1e-10))) / arith_mean if arith_mean > 0 else 0.0

    # Spectral Roll-off (85% accumulated power frequency)
    cumulative_power = np.cumsum(fft_mag)
    threshold = 0.85 * sum_mag
    rolloff_idx = np.where(cumulative_power >= threshold)[0]
    rolloff = fft_freqs[rolloff_idx[0]] if len(rolloff_idx) > 0 else 0.0

    return rms, p2p, dv_dt, snr_db, skewness, kurtosis, crest_factor, centroid, flatness, rolloff, fft_freqs, fft_mag

# ==============================================================================
# --- INGESTION & UI UPDATE ---
# ==============================================================================
def parse_incoming_line(line_str):
    global current_profile_tag, current_soc_from_esp
    line = line_str.strip()
    if "," in line:
        parts = line.split(",")
        if len(parts) == 4:
            try:
                current_profile_tag = parts[0]
                v1 = ((int(parts[1]) * 3.3) / 4095.0) * 2.0
                v2 = ((int(parts[2]) * 3.3) / 4095.0) * 3.2
                current_soc_from_esp = float(parts[3])
                ch1_buffer.append(v1)
                ch2_buffer.append(v2)
            except ValueError:
                pass

def update_dashboard(frame):
    global last_time_step

    if ser is not None:
        try:
            while ser.in_waiting > 0:
                raw_line = ser.readline().decode('utf-8', errors='ignore')
                parse_incoming_line(raw_line)
        except:
            pass
    elif sock is not None:
        try:
            while True:
                data, addr = sock.recvfrom(1024)
                parse_incoming_line(data.decode('utf-8', errors='ignore'))
        except:
            pass

    raw_arr1 = np.array(ch1_buffer)
    raw_arr2 = np.array(ch2_buffer)

    line_ch1.set_data(range(MAX_SAMPLES), signal.medfilt(raw_arr1, 5))
    line_ch2.set_data(range(MAX_SAMPLES), signal.medfilt(raw_arr2, 5))

    raw_active = raw_arr2 if ("9V" in current_profile_tag or "SUPER" in current_profile_tag) else raw_arr1
    mean_v = np.mean(raw_active)

    dt = time.time() - last_time_step
    last_time_step = time.time()

    (rms, p2p, dv_dt, snr_db, skew, kurt, cf, 
     cent, flat, roll, freqs, mags) = extract_full_metrics(raw_active, dt)

    line_fft.set_data(freqs, mags)
    ax_freq.set_ylim(0, max(0.01, np.max(mags) * 1.5))

    if mean_v < 0.2:
        hud_text.set_text(f"[{connection_mode}]\n⚠️ NO BATTERY DETECTED ON MEASUREMENT LANES")
        return line_ch1, line_ch2, line_fft, hud_text

    soh_val, health_status = calculate_physics_soh(p2p, current_profile_tag)
    soh_str = f"{soh_val:.1f}%" if soh_val is not None else "N/A"
    elapsed_sec = int(time.time() - start_time)

    # Black-Box Flight Logging
    if current_profile_tag != "WAITING" and frame % 20 == 0:
        with open(LOG_FILE, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                round(time.time(), 2), current_profile_tag, round(mean_v, 3), 
                round(current_soc_from_esp, 1), round(soh_val, 1) if soh_val else "N/A",
                round(rms, 3), round(p2p, 4), round(dv_dt, 3), round(snr_db, 1),
                round(skew, 3), round(kurt, 2), round(cf, 2), round(cent, 1),
                round(flat, 4), round(roll, 1)
            ])

    hud_text.set_text(
        f"🏷️ PROFILE: {current_profile_tag} | ⚡ VOLTS: {mean_v:.2f}V | 🔋 SOC: {current_soc_from_esp:.1f}% | 🔬 SOH: {soh_str} ({health_status})\n"
        f"📈 [AMPLITUDE & DRIFT] RMS: {rms:.3f}V | P2P: {p2p:.4f}V | dV/dt: {dv_dt:+.2f} mV/s | SNR: {snr_db:.1f} dB\n"
        f"📐 [MOMENTS & SHAPE]   Skewness: {skew:+.3f} | Kurtosis: {kurt:.2f} | Crest Factor: {cf:.2f}\n"
        f"🎯 [SPECTRAL / FFT]    Centroid: {cent:.1f} Hz | Flatness: {flat:.4f} | Roll-off: {roll:.1f} Hz | ⏱️ {elapsed_sec}s"
    )

    return line_ch1, line_ch2, line_fft, hud_text

ani = animation.FuncAnimation(fig, update_dashboard, interval=50, blit=False)
plt.tight_layout(rect=[0, 0, 1, 0.84])
plt.show()

if ser is not None:
    ser.close()
if sock is not None:
    sock.close()