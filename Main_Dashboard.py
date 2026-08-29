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
LOG_FILE = "dashboard_log.csv"

ser = None
sock = None
connection_mode = "searching..."

# Find serial port
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
    except serial.SerialException:
        ser = None

# Fallback to UDP if no serial device found
if ser is None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((UDP_IP, UDP_PORT))
        sock.setblocking(False)
        connection_mode = f"WIRELESS (UDP {UDP_PORT})"
        print(f"Listening on UDP {UDP_PORT}...")
    except socket.error as err:
        print(f"Socket binding failed: {err}")
        exit()

ch1_buffer = collections.deque([0.0] * MAX_SAMPLES, maxlen=MAX_SAMPLES)
ch2_buffer = collections.deque([0.0] * MAX_SAMPLES, maxlen=MAX_SAMPLES)
voltage_history = collections.deque(maxlen=50)
current_profile = "waiting..."
esp_soc = 0.0

start_time = time.time()

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

ax_left = fig.add_subplot(gs[0, 0])
ax_right = fig.add_subplot(gs[0, 1])

for ax, border_color in [(ax_left, '#00FFCC'), (ax_right, '#FFCC00')]:
    ax.set_facecolor('#111622')
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color(border_color)
        spine.set_linewidth(1.5)

ax_left.text(0.05, 0.82, "VOLTAGE MONITOR", color='#00FFCC', fontsize=10, fontweight='bold')
ax_right.text(0.05, 0.82, "SIGNAL METRICS", color='#FFCC00', fontsize=10, fontweight='bold')

text_left = ax_left.text(0.05, 0.20, "Waiting for data...", color='#E0E6ED', fontsize=9.2, linespacing=1.6)
text_right = ax_right.text(0.05, 0.20, "Waiting for data...", color='#E0E6ED', fontsize=9.2, linespacing=1.6)

# Time-Domain
ax_time = fig.add_subplot(gs[1, :])
ax_time.set_facecolor('#111622')
line_ch1, = ax_time.plot([], [], color='#00FFCC', lw=1.6, label="Low Voltage (CH1)")
line_ch2, = ax_time.plot([], [], color='#FF3366', lw=1.6, label="High Voltage (CH2)")
ax_time.set_ylabel("Voltage (V)", color='#A0AEC0', fontsize=9)
ax_time.set_ylim(0, 11)
ax_time.set_xlim(0, MAX_SAMPLES)
ax_time.grid(True, linestyle='--', alpha=0.15, color='#FFFFFF')
ax_time.legend(loc="upper right", framealpha=0.4, facecolor='#111622', edgecolor='#4A5568', fontsize=8.5)
ax_time.tick_params(colors='#A0AEC0', labelsize=8)

# Frequency-Domain
ax_freq = fig.add_subplot(gs[2, :])
ax_freq.set_facecolor('#111622')
line_fft, = ax_freq.plot([], [], color='#FFCC00', lw=1.5, label="FFT Magnitude")
ax_freq.set_xlabel("Frequency (Hz)", color='#A0AEC0', fontsize=9)
ax_freq.set_ylabel("Power", color='#A0AEC0', fontsize=9)
ax_freq.set_xlim(0, 50)
ax_freq.grid(True, linestyle='--', alpha=0.15, color='#FFFFFF')
ax_freq.tick_params(colors='#A0AEC0', labelsize=8)

fig.suptitle(f"Battery Telemetry | Connection: {connection_mode}", 
             fontsize=12, fontweight='bold', color='#FFFFFF', y=0.98)


def calc_soh(p2p, profile):
    if "LI" not in profile:
        return None, "N/A"
    
    v_fresh = 0.040
    v_dead = 0.300
    soh = 100.0 - (((p2p - v_fresh) / (v_dead - v_fresh)) * 20.0)
    soh = max(85.0, min(100.0, 100 - (p2p * 15)))
    
    if soh >= 92.0:
        status = "Good"
    elif soh >= 80.0:
        status = "Fair"
    else:
        status = "Poor"
    return soh, status

def compute_metrics(signal_arr):
    mean_v = np.mean(signal_arr)
    std_v = np.std(signal_arr) + 1e-6

    rms = np.sqrt(np.mean(signal_arr**2))
    p2p = np.max(signal_arr) - np.min(signal_arr)

    voltage_history.append((time.time(), mean_v))
    if len(voltage_history) >= 2:
        dv = voltage_history[-1][1] - voltage_history[0][1]
        dt = voltage_history[-1][0] - voltage_history[0][0]
        dv_dt = (dv / dt) * 1000.0 if dt > 0 else 0.0
    else:
        dv_dt = 0.0

    snr_db = 20.0 * np.log10(max(mean_v / std_v, 1.0))
    kurtosis = np.mean(((signal_arr - mean_v) / std_v)**4)

    ac_signal = signal_arr - mean_v
    fft_mag = np.abs(rfft(ac_signal)) / len(signal_arr)
    fft_freqs = rfftfreq(len(signal_arr), d=1/SAMPLING_FREQ)

    sum_mag = np.sum(fft_mag) + 1e-10
    centroid = np.sum(fft_freqs * fft_mag) / sum_mag
    
    arith_mean = np.mean(fft_mag) + 1e-10
    flatness = np.exp(np.mean(np.log(fft_mag + 1e-10))) / arith_mean

    return rms, p2p, dv_dt, snr_db, kurtosis, centroid, flatness, fft_freqs, fft_mag

def parse_line(line_str):
    global current_profile, esp_soc
    line = line_str.strip()
    if "," in line:
        parts = line.split(",")
        if len(parts) == 4:
            try:
                current_profile = parts[0]
                v1 = ((int(parts[1]) * 3.3) / 4095.0) * 2.0
                v2 = ((int(parts[2]) * 3.3) / 4095.0) * 3.2
                esp_soc = float(parts[3])
                ch1_buffer.append(v1)
                ch2_buffer.append(v2)
            except ValueError:
                pass

def update_gui(frame):
    if ser is not None:
        try:
            while ser.in_waiting > 0:
                parse_line(ser.readline().decode('utf-8', errors='ignore'))
        except serial.SerialException:
            pass
    elif sock is not None:
        try:
            while True:
                data, addr = sock.recvfrom(1024)
                parse_line(data.decode('utf-8', errors='ignore'))
        except BlockingIOError:
            pass
        except socket.error:
            pass

    arr1 = np.array(ch1_buffer)
    arr2 = np.array(ch2_buffer)

    line_ch1.set_data(range(MAX_SAMPLES), signal.medfilt(arr1, 5))
    line_ch2.set_data(range(MAX_SAMPLES), signal.medfilt(arr2, 5))

    active_arr = arr2 if ("9V" in current_profile or "SUPER" in current_profile) else arr1
    mean_v = np.mean(active_arr)

    rms, p2p, dv_dt, snr_db, kurt, cent, flat, freqs, mags = compute_metrics(active_arr)

    line_fft.set_data(freqs, mags)
    ax_freq.set_ylim(0, max(0.01, np.max(mags) * 1.5))

    elapsed = int(time.time() - start_time)

    if mean_v < 0.2:
        text_left.set_text(f"• Profile: DISCONNECTED\n• Status: No Voltage Detected\n• Uptime: {elapsed}s")
        text_right.set_text("• Waiting for active signal...")
        return line_ch1, line_ch2, line_fft, text_left, text_right

    soh_val, health = calc_soh(p2p, current_profile)
    soh_str = f"{soh_val:.1f}% ({health})" if soh_val is not None else "N/A"

    text_left.set_text(
        f"• Profile:      {current_profile}\n"
        f"• Voltage:      {mean_v:.2f} V\n"
        f"• SOC:          {esp_soc:.1f} %\n"
        f"• Health (SOH): {soh_str}"
    )

    text_right.set_text(
        f"• RMS / P2P:    {rms:.3f} V  |  {p2p*1000:.1f} mV\n"
        f"• Drift:        {dv_dt:+.2f} mV/s  |  SNR: {snr_db:.1f} dB\n"
        f"• Kurtosis:     {kurt:.2f}\n"
        f"• Centroid:     {cent:.1f} Hz  |  Flatness: {flat:.4f}"
    )

    if current_profile != "WAITING" and frame % 20 == 0:
        with open(LOG_FILE, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                round(time.time(), 2), current_profile, round(mean_v, 3), 
                round(esp_soc, 1), round(soh_val, 1) if soh_val else "N/A",
                round(rms, 3), round(p2p, 4), round(dv_dt, 3), round(snr_db, 1),
                round(kurt, 2), round(cent, 1), round(flat, 4)
            ])

    return line_ch1, line_ch2, line_fft, text_left, text_right

ani = animation.FuncAnimation(fig, update_gui, interval=50, blit=False)
plt.subplots_adjust(top=0.92, bottom=0.08, left=0.08, right=0.95)
plt.show()

if ser is not None:
    ser.close()
if sock is not None:
    sock.close()