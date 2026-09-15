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
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
CLIENT_SECRETS = os.path.join(CONFIG_DIR, "client_secrets.json")

# ── 1. YouTube 토큰 발급 ───────────────────────────────
print("\n[1/1] YouTube 토큰 발급 중...")
print("브라우저가 다시 열립니다. 동일하게 허용 클릭하세요.\n")

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
yt_flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, YOUTUBE_SCOPES)
yt_creds = yt_flow.run_local_server(port=0)

youtube_token_path = os.path.join(CONFIG_DIR, "youtube_token.json")
with open(youtube_token_path, "w") as f:
    f.write(yt_creds.to_json())
print(f"✅ YouTube 토큰 저장 완료: {youtube_token_path}")

# ── 3. GitHub Secrets 등록 안내 ────────────────────────
print("\n" + "="*60)
print("✅ 토큰 발급 완료!")
print("="*60)
print("\n다음 단계: GitHub Secrets에 아래 내용을 등록하세요.")
print("GitHub 레포 → Settings → Secrets and variables → Actions → New repository secret\n")

with open(youtube_token_path) as f:
    yt_content = f.read()

print("─── Secret 1 ───────────────────────────────────────")
print("이름: YOUTUBE_TOKEN_JSON")
print("값 (아래 전체 복사):")
print(yt_content)
print("="*60)
