import serial
import collections
import numpy as np
from scipy import signal
from scipy.fft import rfft, rfftfreq
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# --- HARDWARE PORT CONFIGURATION ---
SERIAL_PORT = 'COM3'  # Double-check this matches your assigned Windows port!
BAUD_RATE = 115200

# --- BUFFER SETUP ---
MAX_SAMPLES = 200
SAMPLING_FREQ = 100  # Our firmware loop runs at ~100Hz (10ms delays)
raw_buffer = collections.deque([3.6]*MAX_SAMPLES, maxlen=MAX_SAMPLES)

print(f"Opening Dual-Plot Spectral Data Link on {SERIAL_PORT}...")
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
except Exception as e:
    print(f"🛑 LINK ERROR: {e}")
    exit()

# --- CYBER-DASHBOARD TWO-STAGE LAYOUT ---
plt.style.use('dark_background')
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7)) # Stacks 2 subplots vertically
fig.canvas.manager.set_window_title("Smart Battery Telemetry - Advanced DSP HUD")

# Subplot 1: Time Domain Configuration
line_raw, = ax1.plot([], [], label="Raw Unfiltered Signal", color="crimson", alpha=0.4)
line_filtered, = ax1.plot([], [], label="Cleaned Signal (Median Filter)", color="darkturquoise", linewidth=2)
ax1.set_title("Real-Time Telemetry - Time Domain Waveform")
ax1.set_ylabel("Battery Voltage (Volts)")
ax1.set_ylim(3.0, 4.5)
ax1.set_xlim(0, MAX_SAMPLES)
ax1.grid(True, linestyle="--", alpha=0.1)
ax1.legend(loc="upper right")

# Subplot 2: Frequency Domain (FFT) Configuration
line_fft, = ax2.plot([], [], color="gold", linewidth=2, label="Signal Power Spectrum")
ax2.set_title("Real-Time Telemetry - Frequency Spectrum (SciPy FFT)")
ax2.set_xlabel("Frequency (Hz)")
ax2.set_ylabel("Amplitude Magnitude")
ax2.set_xlim(0, SAMPLING_FREQ / 2) # Nyquist Limit: Max readable frequency is half sampling rate
ax2.set_ylim(0, 0.2) # Adjusted height limit to view microvolt ripple peaks clearly
ax2.grid(True, linestyle="--", alpha=0.1)
ax2.legend(loc="upper right")

plt.tight_layout()

# --- PROCESSING LOOP ENGINE ---
def update_plots(frame):
    while ser.in_waiting > 0:
        try:
            packet_line = ser.readline().decode('utf-8').strip()
            if packet_line.isdigit():
                raw_adc = int(packet_line)
                true_voltage = ((raw_adc * 3.3) / 4095.0) * 2.0
                raw_buffer.append(true_voltage)
        except Exception:
            pass

    # 1. Capture Active Data Vectors
    raw_array = np.array(raw_buffer)
    filtered_array = signal.medfilt(raw_array, kernel_size=5)

    # 2. Compute Real Fast Fourier Transform (FFT) on Cleaned Wave
    # We remove the DC baseline offset (subtracting mean) to focus purely on the AC ripple frequencies
    ac_signal = filtered_array - np.mean(filtered_array)
    fft_magnitude = np.abs(rfft(ac_signal)) / MAX_SAMPLES
    fft_frequencies = rfftfreq(MAX_SAMPLES, d=1/SAMPLING_FREQ)

    # 3. Refresh Screen Coordinate Lines Instantly
    line_raw.set_data(range(MAX_SAMPLES), raw_array)
    line_filtered.set_data(range(MAX_SAMPLES), filtered_array)
    line_fft.set_data(fft_frequencies, fft_magnitude)

    return line_raw, line_filtered, line_fft

# Execute asynchronous tracking canvas loop
ani = animation.FuncAnimation(fig, update_plots, blit=True, interval=30, cache_frame_data=False)
plt.show()

ser.close()
print("Pipeline closed successfully.")