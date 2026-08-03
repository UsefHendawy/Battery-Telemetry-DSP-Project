import pandas as pd
import numpy as np
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
import os

# ==============================================================================
# --- MACHINE LEARNING MODEL TRAINING PIPELINE ---
# ==============================================================================
DATASET_FILE = "telemetry_features_db.csv"
MODEL_OUTPUT_FILE = "battery_model.pkl"

print("="*80)
print("🧠 INITIALIZING MACHINE LEARNING TRAINING ENGINE")
print("="*80)

if not os.path.exists(DATASET_FILE):
    print(f"🛑 ERROR: Master dataset file '{DATASET_FILE}' not found!")
    exit()

# 1. LOAD DATASET
df = pd.read_csv(DATASET_FILE)
print(f"📊 Dataset Loaded Successfully! Total Rows: {len(df)}")
print(f"🏷️ Detected Profile Classes:\n{df['label'].value_counts()}\n")

# 2. SEPARATE FEATURES (X) AND TARGET LABELS (Y)
# We feed the 5 statistical vector columns to predict the string 'label'
X = df[["rms", "kurtosis", "spectral_centroid", "spectral_flatness", "peak_to_peak"]]
y = df["label"]

# 3. TRAIN / TEST SPLIT (80% Training Data, 20% Validation Testing)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# 4. INITIALIZE & TRAIN RANDOM FOREST CLASSIFIER
print("⚡ Training Random Forest Multi-Class Classifier...")
model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
model.fit(X_train, y_train)

# 5. MODEL EVALUATION
y_pred = model.predict(X_test)
accuracy = model.score(X_test, y_test)

print("="*80)
print(f"🏆 MODEL TRAINING COMPLETE! Validation Accuracy: {accuracy * 100:.2f}%")
print("="*80)

print("\n📈 Detailed Classification Report:\n")
print(classification_report(y_test, y_pred))

print("\n🧩 Confusion Matrix:\n")
print(confusion_matrix(y_test, y_pred))

# 6. FEATURE IMPORTANCE RANKING
# See which math feature (RMS, Kurtosis, etc.) was most critical to the AI
importances = model.feature_importances_
feature_names = X.columns
print("\n🔬 Feature Importance Breakdown:")
for name, imp in zip(feature_names, importances):
    print(f"  • {name:<20}: {imp*100:.2f}%")

# 7. SAVE TRAINED MODEL FILE
joblib.dump(model, MODEL_OUTPUT_FILE)
print(f"\n💾 Model successfully saved to disk as: '{MODEL_OUTPUT_FILE}'")
print("="*80)