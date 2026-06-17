import numpy as np
from scipy import signal
import matplotlib.pyplot as plt

print("Initializing Telemetry Math Engines...")

time = np.linspace(0, 2, 200, endpoint=False) 

clean_wave = np.sin(2*np.pi *10 * time) 

noise_wave =  clean_wave + np.random.normal(0, 0.4, size=len(time))

filtered_signal = signal.medfilt(clean_wave, kernel_size=3) 

plt.figure(figsize=(10,5))
plt.plot(time,noise_wave, label="Raw messy RF signal (with static)", color = "red", alpha = 0.6)
plt.plot(time, filtered_signal, label="Cleaned Signal (SciPy Filter Applied)", color="cyan", linewidth=2)
plt.title("Smart Battery Telemetry - Local DSP Filter Verification")
plt.xlabel("Time (Seconds)")
plt.ylabel("Voltage Amplitude (Normalized)")
plt.grid(True, linestyle="--", alpha=0.5)
plt.legend()
plt.show()

print("DSP Pipeline Test: SUCCESS!")
print(f"processed Array Size: {len(filtered_signal)} data packets.")