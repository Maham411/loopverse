"""Central configuration for SmogGuard AI.

Every path, threshold and constant used by the pipeline lives here so that
nothing is hidden inside the code.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---- Official challenge inputs (unchanged repository layout) ----
SENSOR_FILES = {
    "batch_1": ROOT / "sensors" / "batch_1_sensor_data.csv",
    "batch_2": ROOT / "sensors" / "batch_2_sensor_data.csv",
}
SENSOR_METADATA = ROOT / "weather" / "sensor_metadata.csv"
WEATHER_HISTORY = ROOT / "weather" / "weather_history.csv"
HOLDOUT_INPUTS = ROOT / "holdout" / "holdout_inputs.csv"
HOLDOUT_WEATHER = ROOT / "holdout" / "holdout_weather.csv"
DOCS_DIR = ROOT / "docs"
PREDICTIONS_TEMPLATE = ROOT / "templates" / "predictions_template.csv"

# ---- Generated outputs ----
PREDICTIONS_CSV = ROOT / "predictions.csv"
ARTIFACTS_DIR = ROOT / "artifacts"
DAILY_CLEAN_CSV = ARTIFACTS_DIR / "daily_pm25_clean.csv"
AUDIT_JSON = ARTIFACTS_DIR / "data_audit.json"
MODEL_REPORT_JSON = ARTIFACTS_DIR / "model_report.json"
# Optional organiser fallback (SPEC section 8). Only used if predictions.csv is missing.
REFERENCE_FORECAST_CSV = ROOT / "reference" / "reference_forecast.csv"

# ---- Rules from SPEC.md ----
HAZARD_THRESHOLD = 165.0          # SPEC section 3: a day IS hazardous if PM2.5 >= 165
# Alarm levels tried when calibrating the hazardous alert (handbook: "calibrate the
# threshold using hazardous recall and false alarms"). Chosen by F1 on September.
ALARM_GRID = [165, 160, 155, 150, 145, 140, 135, 130, 125, 120, 115]
SENTINEL = -999                   # SPEC section 2: -999 means missing/invalid
LOCAL_TZ = "Asia/Karachi"         # Pakistan Standard Time (UTC+5, no DST)
FLATLINE_MIN_RUN = 3              # DOC-06: a sensor stuck for three consecutive days

# Classic US EPA PM2.5 AQI breakpoints. Verified against the data: AQI computed
# from batch_1 PM2.5 with this table reproduces batch_2 exactly for 98.3% of
# sensor-days (the 2024 revision matches only ~10%).
AQI_POINTS = [0, 50, 51, 100, 101, 150, 151, 200, 201, 300, 301, 400, 401, 500]
PM25_POINTS = [0.0, 12.0, 12.1, 35.4, 35.5, 55.4, 55.5, 150.4, 150.5, 250.4,
               250.5, 350.4, 350.5, 500.4]

# Physical floor for a Lahore daily PM2.5 forecast (lowest valid reading in the data is ~19).
MIN_PM25 = 15.0

# Chronological validation split (targets on/before this date are training).
TRAIN_END = "2026-09-30"
RANDOM_SEED = 42

# ---- Coverage: the 15 areas (DOC-13 / sensor_metadata.csv) ----
# Aliases map common spellings (English + Roman Urdu) to the canonical area.
AREA_ALIASES = {
    "Gulberg": ["gulberg", "gulburg", "gulbarg"],
    "DHA": ["dha", "defence", "defense", "d.h.a", "defence housing authority"],
    "Johar Town": ["johar town", "joher town", "johar", "jauhar town"],
    "Model Town": ["model town", "modal town"],
    "Wagah": ["wagah", "wagha", "wahga"],
    "Thokar Niaz Baig": ["thokar niaz baig", "thokar niaz beg", "thokar"],
    "Allama Iqbal Town": ["allama iqbal town", "iqbal town", "aiqbal town"],
    "Shadman": ["shadman"],
    # Note: no plain "cant" alias - "can't" would otherwise match Cantt.
    "Cantt": ["cantt", "cantonment", "lahore cantt"],
    "Faisal Town": ["faisal town", "faysal town"],
    "Township": ["township"],
    "Walled City": ["walled city", "old city", "androon shehr", "andron shehr",
                    "androon lahore", "purana lahore"],
    "Raiwind Road": ["raiwind road", "raiwind rd", "raiwind"],
    "Bahria Town": ["bahria town", "bahria"],
    "Airport Road": ["airport road", "airport rd"],
}

# Places that are clearly NOT covered. Used to refuse confidently instead of
# silently ignoring the location. Anything else unknown is simply not matched.
UNSUPPORTED_PLACES = [
    "karachi", "islamabad", "rawalpindi", "pindi", "quetta", "peshawar", "multan",
    "faisalabad", "gujranwala", "sialkot", "hyderabad", "sargodha", "bahawalpur",
    "sukkur", "abbottabad", "murree", "sheikhupura", "kasur", "gujrat", "sahiwal",
    "delhi", "new delhi", "mumbai", "amritsar", "dubai", "london", "kabul",
    "beijing", "new york", "punjab province",
    # Lahore neighbourhoods without a sensor in this challenge
    "anarkali", "garden town", "samanabad", "ichhra", "iqbal park", "mall road",
    "valencia", "wapda town", "ferozepur road", "canal road", "gulshan-e-ravi",
    "gulshan e ravi", "shahdara", "mughalpura", "green town", "sabzazar",
]
