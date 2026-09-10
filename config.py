import os

# --- MIKROTIK API CONFIGURATION ---
ROUTER_IP = "192.168.88.1" 
ROUTER_USER = "AI"
ROUTER_PASS = "the user's password"
ROUTER_PORT = 8728

TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"
ENABLE_TELEGRAM = True

# --- WAN INTERFACES & PROBE MAPPING ---
# The keys ("ether1", "ether2") must match the interface names in Winbox exactly!
WAN_CONFIG = {
    "ether1": {
        "name": "ISP_A",
        "probe": "8.8.8.8",
        "route_comment": "WAN_A_DEFAULT",
    },
    "ether2": {
        "name": "ISP_B",
        "probe": "1.1.1.1",
        "route_comment": "WAN_B_DEFAULT",
    },
}

SAMPLE_INTERVAL = 2  # Interval sampling (second)

# --- HYSTERESIS / SAFETY SETTINGS ---
CONSECUTIVE_DEGRADED_NEEDED = 2   # number of consecutive DEGRADED samples before failover
CONSECUTIVE_HEALTHY_NEEDED = 3    # number of consecutive NORMAL samples before failback
COOLDOWN_LIMIT = 3               # "Quiet" cycle following a routing change
SAFE_DISTANCES = (1, 2, 3)        # AI can only set distance to one of these values

# --- PATH DIRECTORIES ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
MODELS_DIR = os.path.join(BASE_DIR, "models")

DATASET_PATH = os.path.join(DATASET_DIR, "real_telemetry.csv")
MODEL_PATH = os.path.join(MODELS_DIR, "ai_model.joblib")
SCALER_PATH = os.path.join(MODELS_DIR, "scaler.joblib")
FEATURES_PATH = os.path.join(MODELS_DIR, "feature_names.joblib")

os.makedirs(DATASET_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)
