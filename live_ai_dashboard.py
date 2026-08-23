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
import matplotlib.gridspec as gridspec

warnings.filterwarnings("ignore")

BAUD_RATE = 115200
UDP_IP = "0.0.0.0"
UDP_PORT = 5005
SAMPLING_FREQ = 100
MAX_SAMPLES = 300
LOG_FILE = "telemetry_run_log.csv"

ser = None
sock = None
connection_mode = "searching..."

ports = [
    p.device for p in serial.tools.list_ports.comports()
    if any(k in p.description for k in ["CP210", "CH340", "USB", "Serial"]) or "COM" in p.device
]

for port in ports:
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=0.01)
        connection_mode = f"WIRED ({port})"
        print(f"Connected to ESP32 on {port}")
        break
    except:
        ser = None

if ser is None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((UDP_IP, UDP_PORT))
        sock.setblocking(False)
        connection_mode = f"WIRELESS (UDP {UDP_PORT})"
        print(f"Listening on wireless UDP port {UDP_PORT}...")
    except Exception as e:
        print(f"Port Error: {e}")
        exit()

ch1_buffer = collections.deque([0.0] * MAX_SAMPLES, maxlen=MAX_SAMPLES)
ch2_buffer = collections.deque([0.0] * MAX_SAMPLES, maxlen=MAX_SAMPLES)
voltage_history = collections.deque(maxlen=50)
current_profile_tag = "waiting..."
current_soc_from_esp = 0.0

start_time = time.time()
last_time_step = time.time()

if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp", "profile", "voltage_v", "soc_pct", "soh_pct",
            "rms_v", "p2p_v", "dv_dt_mvs", "snr_db", "skewness", "kurtosis",
            "centroid_hz", "flatness"
        ])

plt.style.use('dark_background')
fig = plt.figure(figsize=(12, 8.5))
fig.patch.set_facecolor('#0B0E14')

gs = gridspec.GridSpec(3, 2, height_ratios=[1.1, 2.0, 2.0], figure=fig, hspace=0.35, wspace=0.15)

ax_card_left = fig.add_subplot(gs[0, 0])
ax_card_right = fig.add_subplot(gs[0, 1])

for ax, border_color in [(ax_card_left, '#00FFCC'), (ax_card_right, '#FFCC00')]:
    ax.set_facecolor('#111622')
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color(border_color)
        spine.set_linewidth(1.5)

# Header Labels
ax_card_left.text(0.05, 0.82, "CORE CELL TELEMETRY", color='#00FFCC', fontsize=10, fontweight='bold')
ax_card_right.text(0.05, 0.82, "REAL-TIME DSP & MOMENTS", color='#FFCC00', fontsize=10, fontweight='bold')

# Dynamic Value Placeholders
text_left = ax_card_left.text(0.05, 0.20, "Waiting for device...", color='#E0E6ED', fontsize=9.2, linespacing=1.6)
text_right = ax_card_right.text(0.05, 0.20, "Initializing digital signal processing...", color='#E0E6ED', fontsize=9.2, linespacing=1.6)

# Time-Domain Voltage Waveform
ax_time = fig.add_subplot(gs[1, :])
ax_time.set_facecolor('#111622')
line_ch1, = ax_time.plot([], [], color='#00FFCC', lw=1.6, label="Low voltage lane (CH1)")
line_ch2, = ax_time.plot([], [], color='#FF3366', lw=1.6, label="High voltage lane (CH2)")
ax_time.set_ylabel("Potential (V)", color='#A0AEC0', fontsize=9)
ax_time.set_ylim(0, 11)
ax_time.set_xlim(0, MAX_SAMPLES)
ax_time.grid(True, linestyle='--', alpha=0.15, color='#FFFFFF')
ax_time.legend(loc="upper right", framealpha=0.4, facecolor='#111622', edgecolor='#4A5568', fontsize=8.5)
ax_time.tick_params(colors='#A0AEC0', labelsize=8)

#Frequency-Domain Power Spectrum
ax_freq = fig.add_subplot(gs[2, :])
ax_freq.set_facecolor('#111622')
line_fft, = ax_freq.plot([], [], color='#FFCC00', lw=1.5, label="Spectral Ripple")
ax_freq.set_xlabel("Frequency (Hz)", color='#A0AEC0', fontsize=9)
ax_freq.set_ylabel("Power Density", color='#A0AEC0', fontsize=9)
ax_freq.set_xlim(0, 50)
ax_freq.grid(True, linestyle='--', alpha=0.15, color='#FFFFFF')
ax_freq.tick_params(colors='#A0AEC0', labelsize=8)

fig.suptitle(f"Battery Telemetry and Digital Signal Processing | Current Link: {connection_mode}", 
             fontsize=12, fontweight='bold', color='#FFFFFF', y=0.98)

# Calculations section for State of Health (SOH) and the Digital Signal Processing (DSP) metrics
def calculate_physics_soh(p2p, profile):
    if "LI" not in profile:
        return None, "N/A (Primary)"
    V_p2p_fresh = 0.020
    V_p2p_degraded = 0.120
    soh = 100.0 - (((p2p - V_p2p_fresh) / (V_p2p_degraded - V_p2p_fresh)) * 20.0)
    soh = max(70.0, min(100.0, soh))
    
    if soh >= 92.0:
        health_status = "Optimal"
    elif soh >= 80.0:
        health_status = "Nominal"
    else:
        health_status = "Degraded"
    return soh, health_status

def extract_dsp_metrics(time_signal):
    mean_v = np.mean(time_signal)
    std_v = np.std(time_signal) if np.std(time_signal) > 0 else 0.0001

    rms = np.sqrt(np.mean(time_signal**2))
    p2p = np.max(time_signal) - np.min(time_signal)

    voltage_history.append((time.time(), mean_v))
    if len(voltage_history) >= 2:
        dv = voltage_history[-1][1] - voltage_history[0][1]
        dt_span = voltage_history[-1][0] - voltage_history[0][0]
        dv_dt = (dv / dt_span) * 1000.0 if dt_span > 0 else 0.0
    else:
        dv_dt = 0.0

    snr_db = 20.0 * np.log10(max(mean_v / std_v, 1.0))
    kurtosis = np.mean(((time_signal - mean_v) / std_v)**4)

    ac_signal = time_signal - mean_v
    fft_mag = np.abs(rfft(ac_signal)) / len(time_signal)
    fft_freqs = rfftfreq(len(time_signal), d=1/SAMPLING_FREQ)

    sum_mag = np.sum(fft_mag)
    centroid = np.sum(fft_freqs * fft_mag) / sum_mag if sum_mag > 0 else 0.0
    arith_mean = np.mean(fft_mag)
    flatness = np.exp(np.mean(np.log(fft_mag + 1e-10))) / arith_mean if arith_mean > 0 else 0.0

    return rms, p2p, dv_dt, snr_db, kurtosis, centroid, flatness, fft_freqs, fft_mag

# --- UPDATE PIPELINE ---
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
    if ser is not None:
        try:
            while ser.in_waiting > 0:
                parse_incoming_line(ser.readline().decode('utf-8', errors='ignore'))
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

    rms, p2p, dv_dt, snr_db, kurt, cent, flat, freqs, mags = extract_dsp_metrics(raw_active)

    line_fft.set_data(freqs, mags)
    ax_freq.set_ylim(0, max(0.01, np.max(mags) * 1.5))

    elapsed_sec = int(time.time() - start_time)

    if mean_v < 0.2:
        text_left.set_text("• Profile: DISCONNECTED\n• Status: No Voltage Detected\n• Active Time: " + f"{elapsed_sec}s")
        text_right.set_text("• DSP Pipeline: IDLE\n• Metrics: Standby\n• FFT Status: Offline")
        return line_ch1, line_ch2, line_fft, text_left, text_right

    soh_val, health_status = calculate_physics_soh(p2p, current_profile_tag)
    soh_display = f"{soh_val:.1f}% ({health_status})" if soh_val is not None else "N/A (Single-Use)"

    # Clean Left Card: Physical Measurements
    text_left.set_text(
        f"• Profile:      {current_profile_tag}\n"
        f"• Active Volts: {mean_v:.2f} V\n"
        f"• Fuel (SOC):   {current_soc_from_esp:.1f} %\n"
        f"• Health (SOH): {soh_display}"
    )

    # Clean Right Card: Computed DSP Metrics
    text_right.set_text(
        f"• RMS / P2P:    {rms:.3f} V  |  {p2p*1000:.1f} mV\n"
        f"• Drift (dV/dt):{dv_dt:+.2f} mV/s  |  SNR: {snr_db:.1f} dB\n"
        f"• Kurtosis:     {kurt:.2f} (DC Baseline: ~3.0)\n"
        f"• Centroid:     {cent:.1f} Hz  |  Flatness: {flat:.4f}"
    )

    # Periodic background logging
    if current_profile_tag != "WAITING" and frame % 20 == 0:
        with open(LOG_FILE, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                round(time.time(), 2), current_profile_tag, round(mean_v, 3), 
                round(current_soc_from_esp, 1), round(soh_val, 1) if soh_val else "N/A",
                round(rms, 3), round(p2p, 4), round(dv_dt, 3), round(snr_db, 1),
                round(kurt, 2), round(cent, 1), round(flat, 4)
            ])

    return line_ch1, line_ch2, line_fft, text_left, text_right

ani = animation.FuncAnimation(fig, update_dashboard, interval=50, blit=False)
plt.subplots_adjust(top=0.92, bottom=0.08, left=0.08, right=0.95)
plt.show()

if ser is not None:
    ser.close()
if sock is not None:
    sock.close()