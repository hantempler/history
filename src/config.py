import os
from dotenv import load_dotenv

# Base paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, 'config')
ENV_PATH = os.path.join(CONFIG_DIR, '.env')
FONT_PATH = os.path.join(CONFIG_DIR, "GmarketSansTTFBold.ttf")

# Load environment variables
load_dotenv(ENV_PATH)

# GCP / Vertex AI
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(CONFIG_DIR, "application_default_credentials.json")
GCP_PROJECT_ID = "project-beba2bf6-d235-4031-ba5"
GCP_LOCATION = "us-central1"

from datetime import datetime

ASSETS_DIR = os.path.join(BASE_DIR, "assets")

EDITION_CONFIG = {
    "history": {
        "data_dir": os.path.join(BASE_DIR, "data", "history"),
        "voice_name": "ko-KR-Wavenet-D",
        "language_code": "ko-KR",
        "top_title": "1분 타임머신",
        "video_suffix": "_역사속오늘.mp4",
        "hook_prompt": "역사 속 오늘, 신비롭고 흥미진진한 시작 알림",
        "closing_prompt": "과거를 통해 오늘을 되돌아보게 하는 여운이 남는 내레이션 대본",
        "closing_quote_prompt": "역사, 시간, 지혜와 관련된 '출처가 명확한 위인들의 명언(발언자 포함)' 텍스트"
    },
    "history_en": {
        "data_dir": os.path.join(BASE_DIR, "data", "history_en"),
        "voice_name": "en-US-Journey-F",
        "language_code": "en-US",
        "top_title": "1 Min Time Machine",
        "video_suffix": "_on_this_day.mp4",
        "hook_prompt": "Mysterious and exciting opening for 'On This Day in History'",
        "closing_prompt": "A lingering closing narration reflecting on today through the past",
        "closing_quote_prompt": "A profound quote about history, time, or wisdom from a clear source (including the speaker)"
    }
}

for ed in EDITION_CONFIG:
    os.makedirs(EDITION_CONFIG[ed]["data_dir"], exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)

DATA_DIR = EDITION_CONFIG["history"]["data_dir"] # Default backward compatibility

def get_daily_dir(target_date_str=None, edition="history"):
    if target_date_str is None:
        target_date_str = datetime.now().strftime("%Y%m%d")
        
    formatted_date = f"{target_date_str[:4]}-{target_date_str[4:6]}-{target_date_str[6:8]}"
    daily_dir = os.path.join(EDITION_CONFIG[edition]["data_dir"], formatted_date)
    os.makedirs(daily_dir, exist_ok=True)
    return daily_dir
