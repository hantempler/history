import os
import sys
import json
import re
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
TOKEN_PATH = os.path.join(CONFIG_DIR, "youtube_token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

CATEGORY_EDUCATION = "27"
DEFAULT_TAGS = ["역사", "쇼츠", "역사쇼츠", "Shorts", "다큐멘터리", "오늘의역사"]


def get_audio_duration_sec(path: str) -> float:
    """ffmpeg으로 오디오 길이(초) 측정"""
    if not os.path.exists(path):
        return 12.0
    try:
        ffmpeg_exe = shutil.which("ffmpeg") or "ffmpeg"
        cmd = [ffmpeg_exe, "-i", path]
        res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
        if m:
            h, m_val, s = m.groups()
            return int(h) * 3600 + int(m_val) * 60 + float(s)
    except Exception:
        pass
    return 12.0


def build_service():
    """OAuth 토큰으로 YouTube v3 클라이언트 빌드 및 자동 갱신."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    # 로컬 config 확인 후 부모 config 폴백 확인
    token_p = TOKEN_PATH
    if not os.path.exists(token_p):
        root_token = os.path.join(os.path.dirname(BASE_DIR), "config", "youtube_token.json")
        if os.path.exists(root_token):
            token_p = root_token

    if not os.path.exists(token_p):
        raise FileNotFoundError(f"[YouTube] OAuth 토큰 파일 없음: {TOKEN_PATH}")

    creds = Credentials.from_authorized_user_file(token_p, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_p, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
            print("  [YouTube] 토큰 자동 갱신 완료")
        else:
            raise RuntimeError("  [YouTube] 토큰 무효: 재발급 필요")
    return build("youtube", "v3", credentials=creds)


def build_video_metadata(script_data: dict, script_path: str = "", edition="history") -> dict:
    """masterpiece_script.json 데이터를 파싱하여 고품격 SEO 메타데이터 생성."""
    is_english = edition in ("history_en", "en") or script_data.get("lang") == "en"

    corner_name = script_data.get("corner_name", "History Time Machine" if is_english else "역사 타임머신")
    event_title = script_data.get("event_title", "Turning Point in History" if is_english else "역사의 순간")
    hook_question = script_data.get("hook_question", "")
    why_desc = script_data.get("why_today_desc", "")
    scenes = script_data.get("scenes", [])
    bgm_name = script_data.get("bgm", "ancient_rite.mp3")

    clean_corner_tag = re.sub(r'[\s·\-\.\/]', '', corner_name)

    # 1. 제목 (최대 100자 이내)
    if hook_question:
        title = f"[{corner_name}] {event_title} | {hook_question} #Shorts"
    else:
        title = f"[{corner_name}] {event_title} #Shorts"
    if len(title) > 98:
        title = title[:94] + "... #Shorts"

    # 2. 타임라인 목차 조립 (타임코드 + 씬 소제목)
    intro_label = "Today in History" if is_english else "오늘의 역사 타임머신"
    timeline_lines = [f"00:00 [Intro] {intro_label}"]
    accum_sec = 4  # 인트로 커버 4.2초
    script_dir = os.path.dirname(os.path.abspath(script_path)) if script_path else ""

    for sc in scenes:
        s_num = sc.get("scene_number", 1)
        d_title = sc.get("display_title", "").strip()

        m_val = accum_sec // 60
        s_val = accum_sec % 60
        timecode = f"{m_val:02d}:{s_val:02d}"

        tag_name = f"Scene {s_num}" if is_english else f"씬 {s_num}"
        if d_title:
            timeline_lines.append(f"{timecode} [{tag_name}] {d_title}")
        else:
            timeline_lines.append(f"{timecode} [{tag_name}]")

        scene_dur = 12
        if script_dir:
            aud_p = os.path.join(script_dir, "audio", f"scene{s_num}.mp3")
            if os.path.exists(aud_p):
                scene_dur = int(round(get_audio_duration_sec(aud_p)))
        accum_sec += max(6, scene_dur)

    m_val = accum_sec // 60
    s_val = accum_sec % 60
    outro_label = "Questions History Left Behind" if is_english else "역사가 남긴 질문"
    timeline_lines.append(f"{m_val:02d}:{s_val:02d} [Epilogue] {outro_label}")

    timeline_text = "\n".join(timeline_lines)

    # 3. 본문 설명 (Description) 조립
    outro_q = script_data.get("outro_debate", {}).get("question_a_2", "Lessons from history" if is_english else "역사의 교훈과 성찰")
    if is_english:
        desc_blocks = [
            f"⏳ {hook_question}\n{why_desc}".strip(),
            f"📖 [Timeline & Chapters]\n{timeline_text}",
            f"🏛️ [Visual Archives & Credits]\n• Historical Archives: Wikimedia Commons & Public Domain Records\n• AI Reconstruction: Google Vertex AI Visual Engine\n• Music: {bgm_name} (Royalty Free Archive)",
            f"💬 [Question to Ponder]\n\"{outro_q}\"",
            f"#history #onthisday #documentary #shorts #worldhistory #history_en"
        ]
        default_lang = "en"
        base_tags = ["history", "onthisday", "shorts", "documentary", "worldhistory", "history_en"]
    else:
        desc_blocks = [
            f"⏳ {hook_question}\n{why_desc}".strip(),
            f"📖 [오늘의 역사 타임라인 & 챕터]\n{timeline_text}",
            f"🏛️ [시각 사료 및 제작 크레딧]\n• 역사 사료: 위키미디어 커먼즈(Wikimedia Commons) 및 공공 역사 아카이브\n• AI 고증 복원: Google Vertex AI 시각화 모델\n• 배경음악: {bgm_name} (Royalty Free Archive)",
            f"💬 [생각해볼 질문]\n\"{outro_q}\"",
            f"#역사 #오늘의역사 #쇼츠 #Shorts #다큐멘터리 #{clean_corner_tag}"
        ]
        default_lang = "ko"
        base_tags = list(DEFAULT_TAGS)

    desc = "\n\n".join(desc_blocks)
    if len(desc) > 4800:
        desc = desc[:4800]

    # 4. 태그 조립 (최대 15개)
    tags = list(base_tags)
    tags.append(clean_corner_tag)
    if event_title:
        tags.extend([w for w in re.findall(r'[\w가-힣]+', event_title) if len(w) >= 2])
    seen = set()
    unique_tags = []
    for t in tags:
        clean_t = t.strip()
        if clean_t and clean_t not in seen:
            seen.add(clean_t)
            unique_tags.append(clean_t)

    return {
        "title": title,
        "description": desc,
        "tags": unique_tags[:15],
        "defaultLanguage": default_lang,
        "defaultAudioLanguage": default_lang
    }


def upload_masterpiece_video(video_path: str, script_path: str, privacy: str = "private", edition: str = "history") -> dict:
    """최종 렌더링된 마스터피스 영상을 유튜브 쇼츠로 자동 업로드."""
    from googleapiclient.http import MediaFileUpload

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"[YouTube] 업로드할 영상 파일이 존재하지 않습니다: {video_path}")
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"[YouTube] 대본 파일이 존재하지 않습니다: {script_path}")

    with open(script_path, "r", encoding="utf-8") as f:
        script_data = json.load(f)

    meta = build_video_metadata(script_data, script_path=script_path, edition=edition)

    print("\n==================================================================")
    print(f"🎬 [YouTube Shorts 자동 업로드 시작 - {edition}] ({privacy} 모드)")
    print(f"  📌 영상 파일: {os.path.basename(video_path)}")
    print(f"  📌 유튜브 제목: {meta['title']}")
    print(f"  📌 언어 설정: defaultLanguage={meta['defaultLanguage']}")
    print("==================================================================")

    youtube = build_service()

    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": meta["tags"],
            "categoryId": CATEGORY_EDUCATION,
            "defaultLanguage": meta["defaultLanguage"],
            "defaultAudioLanguage": meta["defaultAudioLanguage"]
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
