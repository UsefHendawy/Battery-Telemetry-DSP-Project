import serial
import collections
import numpy as np
from scipy import signal
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# --- HARDWARE PORT CONFIGURATION ---
SERIAL_PORT = 'COM3'  # Make sure this matches your Device Manager COM port!
BAUD_RATE = 115200

# --- LIVE BUFFER INITIALIZATION ---
# We keep a rolling memory buffer of exactly 200 samples (~2 seconds of data)
MAX_SAMPLES = 200
time_buffer = collections.deque([0]*MAX_SAMPLES, maxlen=MAX_SAMPLES)
raw_buffer = collections.deque([3.6]*MAX_SAMPLES, maxlen=MAX_SAMPLES)
filtered_buffer = collections.deque([3.6]*MAX_SAMPLES, maxlen=MAX_SAMPLES)

# Global sample counter
sample_count = 0

# Establish hardware link
print(f"Connecting to live data link on {SERIAL_PORT}...")
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
except Exception as e:
    print(f"🛑 LINK ERROR: Could not open port {SERIAL_PORT}. Reason: {e}")
    exit()

# --- CANVAS LAYOUT SETUP ---
plt.style.use('dark_background')  # Sleek cyber-aesthetic
fig, ax = plt.subplots(figsize=(10, 5))
fig.canvas.manager.set_window_title("Smart Battery Telemetry - Live Core Dashboard")

# Initialize the two moving waveform graphic lines
line_raw, = ax.plot([], [], label="Raw Unfiltered Signal", color="crimson", alpha=0.4)
line_filtered, = ax.plot([], [], label="Cleaned Signal (SciPy Median Filter)", color="darkturquoise", linewidth=2)

ax.set_title("Real-Time Battery Telemetry Stream", fontsize=14, color="white")
ax.set_xlabel("Elapsed Samples")
ax.set_ylabel("Battery Voltage (Volts)")
ax.set_ylim(3.0, 4.5)  # Constrained safely to standard lithium bounds
ax.set_xlim(0, MAX_SAMPLES)
ax.grid(True, linestyle="--", alpha=0.2)
ax.legend(loc="upper right")

# --- THE REAL-TIME ENGINE LOOP ---
def update_dashboard(frame):
    global sample_count
    
    # Read all pending data packets waiting in the physical USB queue
    while ser.in_waiting > 0:
        try:
            packet_line = ser.readline().decode('utf-8').strip()
            
            if packet_line.isdigit():
                raw_adc = int(packet_line)
                
                # RECONSTRUCTION MATH: Turn raw 12-bit integer back to true voltage
                true_voltage = ((raw_adc * 3.3) / 4095.0) * 2.0
                
                # Push newest metrics into the rolling memory queues
                sample_count += 1
                raw_buffer.append(true_voltage)
                
        except Exception:
            pass # Shield the pipeline against malformed serial bits
            
    # DSP PIPELINE: Extract active array window and pass it to SciPy filter
    raw_array = np.array(raw_buffer)
    filtered_array = signal.medfilt(raw_array, kernel_size=5)
    
    # Refresh graphic line coordinates instantly
    line_raw.set_data(range(MAX_SAMPLES), raw_array)
    line_filtered.set_data(range(MAX_SAMPLES), filtered_array)
    
    return line_raw, line_filtered

# Launch the asynchronous real-time tracking animation loop
ani = animation.FuncAnimation(fig, update_dashboard, blit=True, interval=30, cache_frame_data=False)
plt.show()

# Safely park the port when the UI window is manually closed
ser.close()
print("\nSerial pipe safely parked. Pipeline closed successfully.")