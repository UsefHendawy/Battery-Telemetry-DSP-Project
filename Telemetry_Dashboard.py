import numpy as np
from scipy import signal
import matplotlib.pyplot as plt

def extract_signal_features(data_array):
    """
    Manually extracts statistical descriptors from a data stream chunk.
    """
    rms = np.sqrt(np.mean(data_array**2))
    peak_to_peak = np.max(data_array) - np.min(data_array) 

    return rms, peak_to_peak

print ("Initializing Advanced Smart Battery Telemetry Dashboard...")

# Simulate 5 seconds of an operational battery voltage ripple (100Hz sampling rate)
time = np.linspace(0, 5, 500, endpoint=False)

# Generate a mock 10Hz electrochemical oscillation signature
base_signal = np.sin(2 * np.pi * 10 * time)

# Inject random high-frequency over-the-air electromagnetic static noise
noisy_telemetry = base_signal + np.random.normal(0, 0.5, size=len(time))

# Use SciPy to apply a digital filter profile to clean up the data array
cleaned_telemetry = signal.medfilt(noisy_telemetry, kernel_size=5)

# Extract features from our cleaned dataset
calc_rms, calc_p2p = extract_signal_features(cleaned_telemetry)

print("\n--- EXTRACTED SIGNAL FEATURES ---")
print(f"Signal energy (RMS Value): {calc_rms:.4f}")
print(f"Voltage Delta (Peak-to-Peak): {calc_p2p:.4f} units.")
print("---------------------------------\n")

# Render the multi-plot data visualizer dashboard
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6))

# Plot 1: Raw Messy Telemetry Signal
ax1.plot(time, noisy_telemetry, color="crimson", alpha=0.6, label="Raw Noisy RF Stream")
ax1.set_title("Smart Battery Telemetry - Real-Time Dashboard Interface")
ax1.set_ylabel("Voltage Ripple")
ax1.grid(True, linestyle="--", alpha=0.5)
ax1.legend(loc="upper right")

# Plot 2: Cleaned Signal After Local DSP Processing
ax2.plot(time, cleaned_telemetry, color="darkturquoise", linewidth=2, label="Processed Signal (SciPy Filter Applied)")
ax2.set_xlabel("Time (Seconds)")
ax2.set_ylabel("Voltage Ripple")
ax2.grid(True, linestyle="--", alpha=0.5)
ax2.legend(loc="upper right")

plt.tight_layout()
plt.show()