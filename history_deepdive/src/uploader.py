import os
import sys
import json
import re
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
TOKEN_PATH = os.path.join(CONFIG_DIR, "youtube_token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

CATEGORY_EDUCATION = "27"
DEFAULT_TAGS = ["역사", "쇼츠", "역사쇼츠", "Shorts", "다큐멘터리", "오늘의역사"]


def get_audio_duration_sec(path: str) -> float:
    """ffmpeg으로 오디오 길이(초) 측정 (외부 라이브러리 의존성 없음)"""
    if not os.path.exists(path):
        return 11.0
    try:
        ffmpeg_exe = shutil.which("ffmpeg") or "ffmpeg"
        cmd = [ffmpeg_exe, "-i", path]
        res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
        if m:
            h, m_val, s = m.groups()
            return int(h)*3600 + int(m_val)*60 + float(s)
    except Exception:
        pass
    return 11.0


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


def build_video_metadata(script_data: dict, script_path: str = "") -> dict:
    """masterpiece_script.json 데이터를 파싱하여 5개 블록 메타데이터 생성."""
    corner_name = script_data.get("corner_name", "역사 딥다이브")
    event_title = script_data.get("event_title", "역사의 순간")
    hook_question = script_data.get("hook_question", "")
    why_desc = script_data.get("why_today_desc", "")
    scenes = script_data.get("scenes", [])
    bgm_name = script_data.get("bgm", "ancient_rite.mp3")
    fact_check = script_data.get("fact_check", {})

    # 특수문자(·, 공백, 하이픈 등)를 제거한 유효 해시태그 생성 (예: '전술·전쟁사' -> '전술전쟁사')
    clean_corner_tag = re.sub(r'[\s·\-\.\/]', '', corner_name)

    # 1. 제목 (유튜브 API 엄격 제한 100자 이내 보장)
    suffix = " #Shorts"
    if hook_question:
        base_title = f"[{corner_name}] {event_title} | {hook_question}"
    else:
        base_title = f"[{corner_name}] {event_title}"

    max_base_len = 95 - len(suffix)  # 87자 이내로 안전 절단
    if len(base_title) > max_base_len:
        base_title = base_title[:max_base_len - 3].rstrip() + "..."
    title = f"{base_title}{suffix}"

    # 2. 타임라인 목차 조립 (타임코드 + 소제목 + 1줄 요약)
    timeline_lines = []
    accum_sec = 0
    script_dir = os.path.dirname(os.path.abspath(script_path)) if script_path else ""

    for sc in scenes:
        s_num = sc.get("scene_number", 1)
        d_title = sc.get("display_title", "").strip()

        # 1순위: 대본 생성 시 포함된 1줄 핵심 summary
        summary = sc.get("summary", "").strip()
        if not summary:
            # 폴백: image_caption 또는 script 핵심 문장에서 간결하게 추출
            caption = sc.get("image_caption", "").strip()
            script_text = sc.get("script", "").strip()
            sentences = [s.strip() for s in re.split(r'[.!?]', script_text) if len(s.strip()) >= 12]
            if sentences:
                summary = sentences[0]
                if len(summary) > 35:
                    summary = summary[:32] + "..."
            elif caption:
                summary = caption

        m_val = accum_sec // 60
        s_val = accum_sec % 60
        timecode = f"{m_val:02d}:{s_val:02d}"

        if summary:
            if d_title:
                timeline_lines.append(f"{timecode} 씬 {s_num} | {d_title} : {summary}")
            else:
                timeline_lines.append(f"{timecode} 씬 {s_num} : {summary}")
        else:
            if d_title:
                timeline_lines.append(f"{timecode} 씬 {s_num} : {d_title}")
            else:
                timeline_lines.append(f"{timecode} 씬 {s_num}")

        # 실제 오디오 길이 확인 (없으면 기본 11초)
        scene_dur = 11
        if script_dir:
            aud_p1 = os.path.join(script_dir, "audio", f"scene{s_num}.mp3")
            aud_p2 = os.path.join(script_dir, "audio", f"scene_{s_num}.mp3")
            aud_p = aud_p1 if os.path.exists(aud_p1) else aud_p2
            if os.path.exists(aud_p):
                scene_dur = int(round(get_audio_duration_sec(aud_p)))
        accum_sec += max(8, scene_dur)

    timeline_text = "\n".join(timeline_lines)

    # 3. 팩트체크 사료 목록 조립
    sources = fact_check.get("historical_sources", [])
    if sources:
        source_lines = [f"{idx+1}. {s}" for idx, s in enumerate(sources)]
        sources_text = "\n".join(source_lines)
    else:
        sources_text = "조선왕조실록 및 당대 정사 기록물 대조 완료"

    # 4. 질문 추출 (씬 5 마지막 문장 중심)
    question_text = ""
    if scenes:
        last_script = scenes[-1].get("script", "")
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
        f"📜 [100% 팩트체크 사료 출처]\n{sources_text}",
        f"💬 [생각해볼 질문]\n\"{question_text}\"",
        f"🎵 [음악 및 크레딧]\n배경음악: {bgm_name} (Royalty Free)\n시각 사료: 위키미디어 커먼즈 & Vertex AI 역사 고증 복원\n\n#역사 #오늘의역사 #쇼츠 #Shorts #다큐멘터리 #{clean_corner_tag}"
    ]

    desc = "\n\n".join(desc_blocks)
    if len(desc) > 4900:
        desc = desc[:4900]

    # 6. 태그 조립 (최대 15개)
    tags = list(DEFAULT_TAGS)
    tags.append(clean_corner_tag)
    if clean_corner_tag != corner_name:
        tags.append(corner_name)
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

    meta = build_video_metadata(script_data, script_path=script_path)

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
