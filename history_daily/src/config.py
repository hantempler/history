import os
import sys
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_DIR = os.path.dirname(BASE_DIR)

CONFIG_DIR = os.path.join(BASE_DIR, 'config')
ENV_PATH = os.path.join(CONFIG_DIR, '.env')
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

CRED_PATH = os.path.join(CONFIG_DIR, "application_default_credentials.json")
if os.path.exists(CRED_PATH):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CRED_PATH

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "project-beba2bf6-d235-4031-ba5")
GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")

FONT_MAIN = os.path.join(CONFIG_DIR, "GmarketSansTTFBold.ttf")
FONT_TITLE = os.path.join(CONFIG_DIR, "BlackHanSans-Regular.ttf")

ASSETS_DIR = os.path.join(BASE_DIR, "assets")
DATA_DIR = os.path.join(BASE_DIR, "data")

BGM_DIR = os.path.join(ASSETS_DIR, "bgm")

CANVAS_W = 1080
CANVAS_H = 1920
FPS = 30

TTS_CONFIG = {
    "voice_name": "ko-KR-Neural2-C",
    "language_code": "ko-KR",
    "speed_main": 1.06,
    "speed_fast": 1.14,
    "pitch": -0.5
}

os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

def get_daily_dir(target_date_str=None):
    if target_date_str is None:
        target_date_str = datetime.now().strftime("%Y%m%d")
    clean_date = target_date_str.replace("-", "")
    formatted_date = f"{clean_date[:4]}-{clean_date[4:6]}-{clean_date[6:8]}"
    daily_dir = os.path.join(DATA_DIR, formatted_date)
    os.makedirs(daily_dir, exist_ok=True)
    return daily_dir
