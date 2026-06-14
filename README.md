# Smart Battery & Supercapacitor Telemetry System
A system built to capture electrochemical degradation and voltage signatures from a physical lithium-ion battery cell and a supercapacitor bank. It will transmite the signal over a distance and estimate the battery health by processing it through Python DSP and Machine Learning. 

## Pre-start phase (Phase 0): Setting everything up. Currently configuring my VS code settings, terminal settings, and tracking milestones. Also learning how to properly use github! 

### Phase 1: 
1. Physical System: It will use a lithium ion pouch cell and once it works fully, a supercapacitor bank will be used as well.
2. Aquiring node: Using a ESP32 microcontroller, this node will monitor and collect the raw electrochemical degradation signals and voltage fluctuations.
3. Local information node: This will use a 0.96 inch OLED screen to display the real-time statistics of the battery.
4. Over Air Link: Information will be transmitted as digital data packets across a sub-1GHz RF space.
5. Capture node: A hand built directional antenna which will route the RF waves into an RTL-SDR receiver dongle.
6. DSP & AI Enginer: A laptop dashboard which will compute Fast Fourier Transforms (FFT), and also extract statistical features such as RMS, Kurtosis, Spectral Centroid. This dashboard will also drive a machine learning model to evaluate the State of Health (SOH) and classify the active power source.

