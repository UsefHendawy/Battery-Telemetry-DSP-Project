import pandas as pd
import numpy as np
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error
import os

KAGGLE_CSV = "nasa_battery_processed.csv"
MODEL_OUTPUT = "soh_regressor_model.pkl"

print("="*80)
print("🔬 TRAINING NASA LAB-CALIBRATED CONTINUOUS SOH REGRESSOR")
print("="*80)

if not os.path.exists(KAGGLE_CSV):
    print(f"🛑 Error: '{KAGGLE_CSV}' not found! Place your Kaggle NASA CSV in workspace.")
    exit()

df = pd.read_csv(KAGGLE_CSV)

# Extract NASA Lab Features
# Look for standard column names in processed Kaggle dataset
voltage_col = 'voltage' if 'voltage' in df.columns else 'Voltage_measured'
cycle_col = 'cycle' if 'cycle' in df.columns else 'Capacity'
soh_col = 'soh' if 'soh' in df.columns else 'Capacity'

X = df[[voltage_col, cycle_col]].copy()
X.columns = ['voltage', 'cycle']
y = df[soh_col]

# If SOH is raw capacity (e.g. 1.4Ah to 2.0Ah), convert to %
if y.max() <= 2.5:
    y = (y / y.max()) * 100.0

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

reg_model = RandomForestRegressor(n_estimators=100, random_state=42)
reg_model.fit(X_train, y_train)

preds = reg_model.predict(X_test)
rmse = np.sqrt(mean_squared_error(y_test, preds))

print(f"🏆 NASA SOH Regressor Trained! SOH Prediction Error: ±{rmse:.2f}% SOH")

joblib.dump(reg_model, MODEL_OUTPUT)
print(f"💾 Saved SOH Regressor model to '{MODEL_OUTPUT}'")
print("="*80)