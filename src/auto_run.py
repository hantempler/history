import os
import sys
import time
import argparse
from datetime import datetime, timezone, timedelta

# GitHub Actions 서버는 UTC 기준. 한국 시간(KST = UTC+9)으로 날짜/요일 판단
KST = timezone(timedelta(hours=9))

# Add src to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.wiki_scraper import scrape_wiki_onthisday
from src.script_gen import run_script_gen
from src.tts_gen import run_tts_gen
from src.renderer_1_thumb import run_renderer_thumb
from src.renderer_2_video import run_renderer_video
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials


# ---------------------------------------------------------------------------
# 재시도 유틸리티
# ---------------------------------------------------------------------------
def run_with_retry(func, step_name, max_attempts=3, wait_seconds=30, *args, **kwargs):
    """
    주어진 함수를 최대 max_attempts 회까지 재시도합니다.
    성공 시 True, 모든 시도 실패 시 마지막 예외를 raise 합니다.
    """
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            print(f"[{step_name}] 시도 {attempt}/{max_attempts} ...")
            result = func(*args, **kwargs)
            print(f"[{step_name}] [SUCCESS] 성공 (시도 {attempt}회)")
            return result
        except Exception as e:
            last_exc = e
            print(f"[{step_name}] [FAIL] 실패 (시도 {attempt}회): {e}")
            if attempt < max_attempts:
                print(f"[{step_name}] {wait_seconds}초 후 재시도합니다...")
                time.sleep(wait_seconds)
    
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"[{step_name}] 실행 횟수(max_attempts)가 잘못 설정되었습니다.")


# ---------------------------------------------------------------------------
# 각 단계 완료 여부 체크 헬퍼
# ---------------------------------------------------------------------------
def _is_step_done(daily_dir, marker_filename):
    """
    중간 결과 파일이 존재하고 크기가 0 이상이면 해당 단계가 완료된 것으로 간주합니다.
    재시도(retry) 시 이미 완료된 단계를 건너뛸 수 있습니다.
    """
    path = os.path.join(daily_dir, marker_filename)
    return os.path.exists(path) and os.path.getsize(path) > 0


# ---------------------------------------------------------------------------
# 단계별 완료 마커 파일 정의
# (각 단계 함수가 생성하는 대표 출력 파일)
# ---------------------------------------------------------------------------
STEP_MARKERS = {
    "scrape":    "1_all_titles.json",   # scraper.py 출력
    "script":    "3_script.json",       # script_gen.py 출력
    "tts":       "4_audio_hook.mp3",    # tts_gen.py 출력 (hook이 첫 번째)
    "thumb":     "5_thumbnail.png",     # renderer_1_thumb.py 출력 (추정)
    # video: video_path 자체로 체크하므로 여기선 제외
}


# ---------------------------------------------------------------------------
# GDrive / YouTube 업로드
# ---------------------------------------------------------------------------
def _get_video_path(target_date, edition):
    """영상 파일 경로를 반환하는 공통 헬퍼"""
    from src.config import EDITION_CONFIG, get_daily_dir
    video_suffix = EDITION_CONFIG[edition]['video_suffix']
    daily_dir = get_daily_dir(target_date, edition)
    video_filename = f"{target_date}{video_suffix}"
    video_path = os.path.join(daily_dir, video_filename)
    return video_path, video_filename


def upload_video_to_youtube(target_date, edition):
    """YouTube에 영상 업로드 (OAuth 토큰 방식)"""
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    token_path = os.path.join(BASE_DIR, "config", "youtube_token.json")
    if not os.path.exists(token_path):
        print(f"[YouTube] 토큰 파일 없음 ({token_path}). 업로드 건너뜀.")
        return

    video_path, video_filename = _get_video_path(target_date, edition)
    if not os.path.exists(video_path):
        print(f"[YouTube] 영상 파일 없음: {video_path}")
        return

    from src.config import EDITION_CONFIG, get_daily_dir
    import json
    
    top_title = EDITION_CONFIG[edition]['top_title']
    dt = datetime.strptime(target_date, "%Y%m%d")
    if edition == 'history_en':
        weekdays_en = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        weekday_str = weekdays_en[dt.weekday()]
        date_formatted = f"{dt.strftime('%B')} {dt.day}, {dt.year} ({weekday_str})"
        yt_title = f"{date_formatted} | On This Day in History"
    else:
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        weekday_str = weekdays[dt.weekday()]
        date_formatted = f"{target_date[:4]}.{target_date[4:6]}.{target_date[6:8]}({weekday_str})"
        yt_title = f"{date_formatted} {top_title} 역사 속 오늘"
    
    # 기사 링크 불러오기
    daily_dir = get_daily_dir(target_date, edition)
    articles_path = os.path.join(daily_dir, "2_selected_articles.json")
    
    news_links_text = ""
    if os.path.exists(articles_path):
        try:
            with open(articles_path, "r", encoding="utf-8") as f:
                articles = json.load(f)
            
            if articles:
                if edition == 'history_en':
                    news_links_text = "\n\n[Today's History Highlights]\n"
                else:
                    news_links_text = "\n\n[오늘의 역사 주요 사건]\n"
                for idx, article in enumerate(articles, 1):
                    news_links_text += f"{idx}. {article.get('year')} - {article.get('text')}\n"
        except Exception as e:
            print(f"[YouTube] 기사 불러오기 실패: {e}")

    if edition == 'history_en':
        yt_description = (
            f"{date_formatted} | On This Day in History\n"
            f"{news_links_text}\n"
            "#history #onthisday #documentary #shorts\n"
            f"#{edition}"
        )
    else:
        yt_description = (
            f"{date_formatted} {top_title} 역사 속 오늘\n"
            f"{news_links_text}\n"
            "#역사 #오늘의역사 #다큐멘터리 #쇼츠 #Shorts\n"
            f"#{edition}"
        )

    print(f"[YouTube] '{yt_title}' 업로드 중...")
    try:
        creds = Credentials.from_authorized_user_file(token_path)
        youtube = build('youtube', 'v3', credentials=creds)
        body = {
            'snippet': {
                'title': yt_title,
                'description': yt_description,
                'tags': ['역사', '오늘의역사', '다큐멘터리', '쇼츠', 'Shorts'],
                'categoryId': '25'  # 25 = News & Politics
            },
            'status': {
                'privacyStatus': 'private'  # 비공개. YouTube Studio에서 직접 확인 후 공개로 전환하세요.
            }
        }
        media = MediaFileUpload(video_path, mimetype='video/mp4', resumable=True)
        request = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
        response = request.execute()
        print(f"[YouTube] 업로드 완료! https://youtu.be/{response['id']}")
    except Exception as e:
        print(f"[YouTube] 업로드 실패: {e}")


# ---------------------------------------------------------------------------
# 메인 파이프라인
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="역사 쇼츠 자동화 파이프라인")
    parser.add_argument("--date", type=str, default=None, help="대상 날짜 (YYYYMMDD 형식). 지정하지 않으면 오늘 날짜를 사용합니다.")
    args = parser.parse_args()

    _now_kst = datetime.now(KST)
    target_date = args.date if args.date else _now_kst.strftime("%Y%m%d")

    editions = ["history", "history_en"]

    for edition in editions:
        from src.config import get_daily_dir
        daily_dir = get_daily_dir(target_date, edition)

        print(f"\n\n=== 뉴스 브리핑 무인 파이프라인 ===")
        print(f"[{edition.upper()}] 파이프라인 시작 (대상 날짜: {target_date})")
        print(f"[작업 디렉토리] {daily_dir}")

        try:
            print("\n--- 1. 기사 스크랩 ---")
            if _is_step_done(daily_dir, STEP_MARKERS["scrape"]):
                print(f"[스크랩] [SKIP] 이미 완료된 단계입니다. 건너뜁니다.")
            else:
                run_with_retry(scrape_wiki_onthisday, "스크랩", 3, 30, target_date, edition=edition)

            print("\n--- 2. 대본 작성 ---")
            if _is_step_done(daily_dir, STEP_MARKERS["script"]):
                print(f"[대본] [SKIP] 이미 완료된 단계입니다. 건너뜁니다.")
            else:
                run_with_retry(run_script_gen, "대본", 3, 30, target_date, edition=edition)

            print("\n--- 3. 음성 합성 (TTS) ---")
            if _is_step_done(daily_dir, STEP_MARKERS["tts"]):
                print(f"[TTS] [SKIP] 이미 완료된 단계입니다. 건너뜁니다.")
            else:
                run_with_retry(run_tts_gen, "TTS", 3, 30, target_date, edition=edition)

            print("\n--- 4. 썸네일 생성 ---")
            if _is_step_done(daily_dir, STEP_MARKERS["thumb"]):
                print(f"[썸네일] [SKIP] 이미 완료된 단계입니다. 건너뜁니다.")
            else:
                run_with_retry(run_renderer_thumb, "썸네일", 2, 15, target_date, edition=edition)

            print("\n--- 5. 영상 렌더링 ---")
            video_path, _ = _get_video_path(target_date, edition)
            if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                print(f"[렌더링] [SKIP] 이미 완료된 단계입니다. 건너뜁니다.")
            else:
                run_with_retry(run_renderer_video, "렌더링", 2, 15, target_date, edition=edition)

            print("\n--- 6. YouTube 업로드 ---")
            try:
                run_with_retry(upload_video_to_youtube, "YouTube", 3, 20, target_date, edition=edition)
            except Exception as e:
                print(f"[YouTube] [WARN] 최종 업로드 실패 (파이프라인은 계속): {e}")

            print(f"\n[{edition.upper()}] 모든 작업이 성공적으로 완료되었습니다!")

        except Exception as e:
            print(f"\n[PIPELINE ERROR] 파이프라인 중단: {e}")
            import traceback
            traceback.print_exc()
            print(f"Skipping {edition} due to error, proceeding to next if available.")


if __name__ == "__main__":
    main()
