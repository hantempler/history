"""
[최초 1회 실행] YouTube 토큰 발급 스크립트
==========================================================
이 스크립트를 실행하면 브라우저가 열립니다.
hantempler@gmail.com 으로 로그인 후 권한 허용하면 자동으로 토큰 파일이 저장됩니다.

생성되는 파일:
  config/youtube_token.json   ← YouTube 업로드용

이후 GitHub Secrets에 위 파일의 내용을 등록하면 자동화 완성!
"""

import os
import sys
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# client_secrets.json 위치 탐색 (history_daily 또는 history_deepdive)
MODULES = ["history_daily", "history_deepdive"]
client_secrets_candidates = [
    os.path.join(BASE_DIR, m, "config", "client_secrets.json") for m in MODULES
]
CLIENT_SECRETS = next((p for p in client_secrets_candidates if os.path.exists(p)), None)

if not CLIENT_SECRETS:
    # 기본값으로 history_daily/config/client_secrets.json 사용
    CLIENT_SECRETS = client_secrets_candidates[0]

# ── 1. YouTube 토큰 발급 ───────────────────────────────
print("\n[1/1] YouTube 토큰 발급 중...")
if not os.path.exists(CLIENT_SECRETS):
    print(f"⚠️ client_secrets.json 파일을 찾을 수 없습니다: {CLIENT_SECRETS}")
    print("Google Cloud Console에서 OAuth 클라이언트 ID(데스크톱 앱) JSON을 다운로드하여")
    print("history_daily/config/client_secrets.json 또는 history_deepdive/config/client_secrets.json 에 배치하세요.")
    sys.exit(1)

print("브라우저가 열립니다. 로그인 후 허용을 클릭하세요.\n")

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
yt_flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, YOUTUBE_SCOPES)
yt_creds = yt_flow.run_local_server(port=0)

token_json_str = yt_creds.to_json()
saved_paths = []

for sub_dir in MODULES:
    sub_config = os.path.join(BASE_DIR, sub_dir, "config")
    if os.path.exists(sub_config):
        sub_token = os.path.join(sub_config, "youtube_token.json")
        with open(sub_token, "w", encoding="utf-8") as f:
            f.write(token_json_str)
        saved_paths.append(sub_token)
        print(f"✅ 토큰 저장 완료: {sub_token}")

# ── 3. GitHub Secrets 등록 안내 ────────────────────────
print("\n" + "="*60)
print("✅ 토큰 발급 완료!")
print("="*60)
print("\n다음 단계: GitHub Secrets에 아래 내용을 등록하세요.")
print("GitHub 레포 → Settings → Secrets and variables → Actions → New repository secret\n")

yt_content = token_json_str

print("─── Secret 1 ───────────────────────────────────────")
print("이름: YOUTUBE_TOKEN_JSON")
print("값 (아래 전체 복사):")
print(yt_content)
print("="*60)
