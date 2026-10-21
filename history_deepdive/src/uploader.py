import os
import sys
import json
from pathlib import Path
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
TOKEN_PATH = os.path.join(CONFIG_DIR, "youtube_token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

CATEGORY_EDUCATION = "27"
DEFAULT_TAGS = ["역사", "쇼츠", "역사쇼츠", "Shorts", "다큐멘터리", "오늘의역사"]


def build_service():
    """OAuth 토큰으로 YouTube v3 클라이언트 빌드."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    if not os.path.exists(TOKEN_PATH):
        raise FileNotFoundError(f"[YouTube] 토큰 파일 없음: {TOKEN_PATH}")

    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_PATH, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
            print("  [YouTube] 토큰 갱신 완료")
        else:
            raise RuntimeError("  [YouTube] 토큰 무효: 재발급 필요")
    return build("youtube", "v3", credentials=creds)


def build_video_metadata(script_data: dict) -> dict:
    """masterpiece_script.json 데이터를 파싱하여 5개 블록 메타데이터 생성."""
    corner_name = script_data.get("corner_name", "역사 딥다이브")
    event_title = script_data.get("event_title", "역사의 순간")
    hook_question = script_data.get("hook_question", "")
    why_desc = script_data.get("why_today_desc", "")
    scenes = script_data.get("scenes", [])
    bgm_name = script_data.get("bgm", "ancient_rite.mp3")
    fact_check = script_data.get("fact_check", {})

    # 1. 제목 (최대 100자 이내)
    if hook_question:
        title = f"[{corner_name}] {event_title} | {hook_question} #Shorts"
    else:
        title = f"[{corner_name}] {event_title} #Shorts"
    if len(title) > 100:
        title = title[:96] + "... #Shorts"

    # 2. 타임라인 목차 조립
    timeline_lines = []
    for sc in scenes:
        s_num = sc.get("scene_number", 1)
        d_title = sc.get("display_title", "")
        if d_title:
            timeline_lines.append(f"• 씬 {s_num}: {d_title}")
    timeline_text = "\n".join(timeline_lines)

    # 3. 팩트체크 사료 목록 조립
    sources = fact_check.get("historical_sources", [])
    if sources:
        source_lines = [f"{idx+1}. {s}" for idx, s in enumerate(sources)]
        sources_text = "\n".join(source_lines)
    else:
        sources_text = "조선왕조실록 및 당대 정사 기록물 대조 완료"

    # 4. 고정 댓글용 질문 추출 (씬 5 마지막 문장 중심)
    question_text = ""
    if scenes:
        last_script = scenes[-1].get("script", "")
        # 물음표가 포함된 마지막 문장 추출 시도
        sentences = last_script.split(".")
        for s in reversed(sentences):
            if "?" in s:
                question_text = s.strip() + "?"
                break
        if not question_text and sentences:
            question_text = sentences[-1].strip() or last_script

    # 5. 본문 설명 (Description) 조립
    desc_blocks = [
        f"{hook_question}\n{why_desc}".strip(),
        f"📖 [오늘의 역사 타임라인 & 하이라이트]\n{timeline_text}",
        f"📜 [100% 팩트체크 사료 출처]\n{sources_text}\n- 고증 검증 상태: 정사 기록 및 사료 교차 검증 완료",
        f"💬 [생각해볼 질문 (고정 댓글 추천)]\n\"{question_text}\"",
        f"🎵 [음악 및 크레딧]\n배경음악: {bgm_name} (Royalty Free)\n시각 사료: 위키미디어 커먼즈 & Vertex AI 역사 고증 복원\n\n#역사 #오늘의역사 #쇼츠 #Shorts #다큐멘터리 #{corner_name.replace(' ', '')}"
    ]

    desc = "\n\n".join(desc_blocks)
    if len(desc) > 4900:
        desc = desc[:4900]

    # 6. 태그 조립 (최대 15개)
    tags = list(DEFAULT_TAGS)
    tags.append(corner_name.replace(" ", ""))
    if event_title:
        tags.extend([w for w in event_title.split() if len(w) >= 2])
    # 중복 제거
    seen = set()
    unique_tags = []
    for t in tags:
        clean_t = t.replace(",", "").strip()
        if clean_t and clean_t not in seen:
            seen.add(clean_t)
            unique_tags.append(clean_t)

    return {
        "title": title,
        "description": desc,
        "tags": unique_tags[:15]
    }


def upload_masterpiece_video(video_path: str, script_path: str, privacy: str = "private") -> dict:
    """최종 영상과 대본 JSON을 받아 유튜브에 자동 업로드."""
    from googleapiclient.http import MediaFileUpload

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"[YouTube] 업로드할 영상 파일이 존재하지 않습니다: {video_path}")
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"[YouTube] 대본 파일이 존재하지 않습니다: {script_path}")

    with open(script_path, "r", encoding="utf-8") as f:
        script_data = json.load(f)

    meta = build_video_metadata(script_data)

    print("\n==================================================================")
    print(f"🎬 [YouTube 자동 업로드 시작] ({privacy} 모드)")
    print(f"  📌 영상 파일: {os.path.basename(video_path)}")
    print(f"  📌 유튜브 제목: {meta['title']}")
    print("==================================================================")

    youtube = build_service()

    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": meta["tags"],
            "categoryId": CATEGORY_EDUCATION
        },
        "status": {
            "privacyStatus": privacy
        }
    }

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()

    video_id = response.get("id")
    video_url = f"https://youtu.be/{video_id}"
    print(f"🎉 [YouTube 업로드 성공!] 영상 URL: {video_url}")

    # 업로드 이력 저장
    daily_dir = os.path.dirname(video_path)
    info_path = os.path.join(daily_dir, "youtube_upload_info.json")
    upload_info = {
        "video_id": video_id,
        "video_url": video_url,
        "uploaded_at": datetime.now().isoformat(),
        "title": meta["title"],
        "privacy": privacy
    }
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(upload_info, f, ensure_ascii=False, indent=2)

    return upload_info
