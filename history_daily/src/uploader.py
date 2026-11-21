import os
import sys
import json
import re
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

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
    raw_title = script_data.get("title", "")
    clean_ev_title = re.sub(r'^\[.*?\]\s*', '', raw_title).strip()
    event_title = script_data.get("event_title") or clean_ev_title or ("Turning Point in History" if is_english else "역사의 순간")
    hook_question = script_data.get("hook_question", "")
    scenes = script_data.get("scenes", [])
    bgm_name = script_data.get("bgm", "ancient_rite.mp3")
    fact_check = script_data.get("fact_check", {})
    primary_source = script_data.get("primary_source") or fact_check.get("primary_source", "")
    wiki_title = script_data.get("wiki_page_title", "")

    clean_corner_tag = re.sub(r'[\s·\-\.\/]', '', corner_name)

    # 1. 제목 (유튜브 API 엄격 제한 100자 이내 보장)
    suffix = " #Shorts"
    if hook_question and hook_question not in event_title:
        base_title = f"[{corner_name}] {event_title} | {hook_question}"
    else:
        base_title = f"[{corner_name}] {event_title}"

    max_base_len = 95 - len(suffix)  # 87자 이내로 안전 절단
    if len(base_title) > max_base_len:
        base_title = base_title[:max_base_len - 3].rstrip() + "..."
    title = f"{base_title}{suffix}"

    # 2. 타임라인 목차 조립 (내부 씬 번호 배제, 시청자 중심 스토리 챕터 구성)
    intro_label = "The Beginning of Tragedy" if is_english else "역사의 순간 오프닝"
    timeline_lines = [f"00:00 [오프닝] {intro_label}"]
    accum_sec = 4  # 인트로 커버 3.5~4초
    script_dir = os.path.dirname(os.path.abspath(script_path)) if script_path else ""

    for sc in scenes:
        d_title = sc.get("display_title", "").strip()
        m_val = accum_sec // 60
        s_val = accum_sec % 60
        timecode = f"{m_val:02d}:{s_val:02d}"

        if d_title:
            timeline_lines.append(f"{timecode} {d_title}")
        else:
            caption = sc.get("image_caption", "")
            timeline_lines.append(f"{timecode} {caption or '역사의 현장'}")

        scene_dur = 11
        if script_dir:
            s_num = sc.get("scene_number", 1)
            aud_p = os.path.join(script_dir, "audio", f"scene{s_num}.mp3")
            if os.path.exists(aud_p):
                scene_dur = int(round(get_audio_duration_sec(aud_p)))
        accum_sec += max(6, scene_dur)

    m_val = accum_sec // 60
    s_val = accum_sec % 60
    outro_label = "Historical Reflection" if is_english else "역사가 남긴 질문"
    timeline_lines.append(f"{m_val:02d}:{s_val:02d} [에필로그] {outro_label}")
    timeline_text = "\n".join(timeline_lines)

    # 3. 본문 설명 (Description) 조립: 시놉시스 + 사건 전개 타임라인 + 1차 사료 팩트체크 + 토론 질문 + 크레딧
    hook_point = fact_check.get("killer_hook_point") or fact_check.get("corner_reason") or script_data.get("why_today_desc", "")
    pinned_q = script_data.get("pinned_comment") or script_data.get("outro_debate", {}).get("question_a_2", "역사의 교훈과 성찰")

    if is_english:
        desc_blocks = [
            f"⏳ {hook_question}\n\n{hook_point}".strip(),
            f"📖 [Timeline & Story Chapters]\n{timeline_text}"
        ]
        fc_lines = ["📜 [Verified Historical Sources]"]
        if primary_source:
            fc_lines.append(f"• Primary Source: {primary_source}")
        if wiki_title:
            fc_lines.append(f"• Wikipedia Reference: https://en.wikipedia.org/wiki/{wiki_title}")
        facts = fact_check.get("verified_facts", [])
        if facts:
            fc_lines.append("• Verified Historical Facts:")
            for f_item in facts[:3]:
                fc_lines.append(f"  - {f_item}")
        myth = fact_check.get("debunked_myth", {})
        if myth:
            fc_lines.append(f"• Historical Myth vs Truth:\n  - Myth: {myth.get('myth', '')}\n  - Truth: {myth.get('truth', '')}")
        desc_blocks.append("\n".join(fc_lines))

        desc_blocks.append(f"💬 [Question to Ponder]\n\"{pinned_q}\"")
        desc_blocks.append(
            f"🏛️ [Visual Archives & Credits]\n"
            f"• Historical Archives: Wikimedia Commons & Public Domain Records\n"
            f"• AI Visual Reconstruction: Google Vertex AI Historical Engine\n"
            f"• Background Music: {bgm_name} (Royalty Free Archive)\n\n"
            f"#history #onthisday #documentary #shorts #worldhistory #history_en"
        )
        default_lang = "en"
        base_tags = ["history", "onthisday", "shorts", "documentary", "worldhistory", "history_en"]
    else:
        desc_blocks = [
            f"⏳ {hook_question}\n\n{hook_point}".strip(),
            f"📖 [사건 전개 타임라인]\n{timeline_text}"
        ]
        fc_lines = ["📜 [1차 사료 및 팩트체크 검증]"]
        if primary_source:
            fc_lines.append(f"• 공인 1차 사료: {primary_source}")
        if wiki_title:
            fc_lines.append(f"• 위키백과 사료 문서: https://en.wikipedia.org/wiki/{wiki_title}")
        facts = fact_check.get("verified_facts", [])
        if facts:
            fc_lines.append("• 교차 검증된 핵심 역사적 사실:")
            for f_item in facts[:3]:
                fc_lines.append(f"  - {f_item}")
        myth = fact_check.get("debunked_myth", {})
        if myth:
            fc_lines.append(f"• 역사적 왜곡 바로잡기 (Fact vs Myth):\n  - 통설/오해: {myth.get('myth', '')}\n  - 사료 팩트: {myth.get('truth', '')}")
        desc_blocks.append("\n".join(fc_lines))

        desc_blocks.append(f"💬 [생각해볼 질문 | 댓글로 의견을 나눠주세요]\n\"{pinned_q}\"")
        desc_blocks.append(
            f"🏛️ [시각 사료 및 제작 크레딧]\n"
            f"• 역사 사료: 위키미디어 커먼즈(Wikimedia Commons) 및 공공 역사 아카이브\n"
            f"• AI 고증 복원: Google Vertex AI 시각화 모델\n"
            f"• 배경음악: {bgm_name} (Royalty Free Archive)\n\n"
            f"#역사 #오늘의역사 #쇼츠 #Shorts #다큐멘터리 #{clean_corner_tag}"
        )
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


def compute_scheduled_publish_time(target_date_str: str = None, target_hour: int = 7, target_minute: int = 0, schedule_hour: int = None):
    """KST 기준 목표 예약 공개 시각을 계산하여 (publish_at_iso, privacy_status, log_msg) 반환"""
    hour_to_use = schedule_hour if schedule_hour is not None else target_hour
    now_kst = datetime.now(KST)
    if target_date_str:
        clean = re.sub(r'\D', '', str(target_date_str))
        if len(clean) >= 8:
            y, m, d = int(clean[:4]), int(clean[4:6]), int(clean[6:8])
            sched_kst = datetime(y, m, d, hour_to_use, target_minute, 0, tzinfo=KST)
        else:
            sched_kst = now_kst.replace(hour=hour_to_use, minute=target_minute, second=0, microsecond=0)
    else:
        sched_kst = now_kst.replace(hour=hour_to_use, minute=target_minute, second=0, microsecond=0)

    # 1분 이상의 여유가 있는 미래인 경우 예약 공개(publishAt) 적용
    if sched_kst > (now_kst + timedelta(minutes=1)):
        sched_utc = sched_kst.astimezone(timezone.utc)
        publish_at_iso = sched_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        return publish_at_iso, "private", f"{sched_kst.strftime('%Y-%m-%d %H:%M:%S KST')} (UTC: {publish_at_iso})"
    else:
        # 이미 해당 목표 시각이 경과한 경우 400 에러를 방지하고 즉시 공개(public)
        return None, "public", f"{sched_kst.strftime('%Y-%m-%d %H:%M:%S KST')} (목표 시각 경과 ➔ 즉시 public 공개)"


def upload_masterpiece_video(video_path: str, script_path: str, privacy: str = "scheduled", target_date_str: str = None, schedule_hour: int = 7, edition: str = "history") -> dict:
    """최종 렌더링된 마스터피스 영상을 유튜브 쇼츠로 자동 업로드 (오전 7시 예약 공개 지원)."""
    from googleapiclient.http import MediaFileUpload

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"[YouTube] 업로드할 영상 파일이 존재하지 않습니다: {video_path}")
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"[YouTube] 대본 파일이 존재하지 않습니다: {script_path}")

    with open(script_path, "r", encoding="utf-8") as f:
        script_data = json.load(f)

    meta = build_video_metadata(script_data, script_path=script_path, edition=edition)

    # 공개 상태 및 예약 공개(publishAt) 산출
    publish_at_iso = None
    actual_privacy = privacy
    schedule_info = "수동 지정 모드"

    if privacy == "scheduled":
        publish_at_iso, actual_privacy, schedule_info = compute_scheduled_publish_time(
            target_date_str=target_date_str,
            target_hour=schedule_hour,
            target_minute=0
        )

    print("\n==================================================================")
    print(f"🎬 [YouTube Shorts 자동 업로드 시작 - {edition}] ({actual_privacy} 모드)")
    if publish_at_iso:
        print(f"  ⏰ [예약 공개 설정] {schedule_info}")
    else:
        print(f"  📌 공개 상태: {actual_privacy} ({schedule_info})")
    print(f"  📌 영상 파일: {os.path.basename(video_path)}")
    print(f"  📌 유튜브 제목: {meta['title']}")
    print(f"  📌 언어 설정: defaultLanguage={meta['defaultLanguage']}")
    print("==================================================================")

    youtube = build_service()

    status_dict = {
        "privacyStatus": actual_privacy
    }
    if publish_at_iso:
        # YouTube API 규칙: publishAt이 지정되면 privacyStatus는 반드시 'private'이어야 함
        status_dict["publishAt"] = publish_at_iso
        status_dict["privacyStatus"] = "private"

    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": meta["tags"],
            "categoryId": CATEGORY_EDUCATION,
            "defaultLanguage": meta["defaultLanguage"],
            "defaultAudioLanguage": meta["defaultAudioLanguage"]
        },
        "status": status_dict
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
        "description": meta["description"],
        "tags": meta["tags"],
        "privacy": actual_privacy,
        "publish_at": publish_at_iso,
        "schedule_info": schedule_info,
        "fact_check": {
            "primary_source": script_data.get("primary_source") or script_data.get("fact_check", {}).get("primary_source", ""),
            "verified_facts": script_data.get("fact_check", {}).get("verified_facts", []),
            "debunked_myth": script_data.get("fact_check", {}).get("debunked_myth", {})
        }
    }
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(upload_info, f, ensure_ascii=False, indent=2)

    return upload_info
