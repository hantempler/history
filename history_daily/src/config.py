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

import json

def _resolve_project_id():
    cred = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", CRED_PATH)
    if os.path.exists(cred):
        try:
            with open(cred, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("quota_project_id") or data.get("project_id")
        except Exception:
            pass
    return os.getenv("GCP_PROJECT_ID", "project-092cc259-a7f0-4540-ab3")

GCP_PROJECT_ID = _resolve_project_id()
GCP_LOCATION = os.getenv("GCP_LOCATION", "global")

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

EDITION_CONFIG = {
    "history": {
        "edition_id": "history",
        "lang_code": "ko",
        "dir_name": "ko",
        "voice_name": "ko-KR-Neural2-C",
        "voice_fallback": "ko-KR-Neural2-A",
        "voice_speed": 1.05,
        "voice_pitch": -0.5,
        "video_suffix": "_ko.mp4",
        "yt_category": "27",
        "yt_default_lang": "ko"
    },
    "history_en": {
        "edition_id": "history_en",
        "lang_code": "en",
        "dir_name": "en",
        "voice_name": "en-US-Neural2-J",
        "voice_fallback": "en-US-Journey-F",
        "voice_speed": 1.03,
        "voice_pitch": 0.0,
        "video_suffix": "_en.mp4",
        "yt_category": "27",
        "yt_default_lang": "en"
    }
}

os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

def get_daily_dir(target_date_str=None, edition=None):
    if target_date_str is None:
        target_date_str = datetime.now().strftime("%Y%m%d")
    clean_date = target_date_str.replace("-", "")
    formatted_date = f"{clean_date[:4]}-{clean_date[4:6]}-{clean_date[6:8]}"
    base_daily = os.path.join(DATA_DIR, formatted_date)
    os.makedirs(base_daily, exist_ok=True)

    if edition:
        ed_key = "ko" if edition in ("history", "ko") else ("en" if edition in ("history_en", "en") else edition)
        daily_dir = os.path.join(base_daily, ed_key)
        os.makedirs(daily_dir, exist_ok=True)
        return daily_dir
    return base_daily

