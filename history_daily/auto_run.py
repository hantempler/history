import os
import sys
import time
import json
import argparse
from datetime import datetime, timezone, timedelta

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from src.wiki_collector import collect_wiki_events
from src.script_generator import generate_killer_script
from src.asset_sourcer import source_scene_images
from src.tts_engine import generate_scene_audios
from src.renderer import render_masterpiece_from_script
from src.config import get_daily_dir, CONFIG_DIR

KST = timezone(timedelta(hours=9))


def run_pipeline(target_date_str=None, upload=True, privacy="private"):
    start_time = time.time()

    if not target_date_str:
        now_kst = datetime.now(KST)
        target_date_str = now_kst.strftime("%Y%m%d")

    clean_date = target_date_str.replace("-", "")
    daily_dir = get_daily_dir(clean_date)

    print("==================================================================")
    print(f"🎬 [history_daily 마스터피스 프로덕션 파이프라인 가동]")
    print(f"📅 대상 날짜 (KST): {clean_date[:4]}-{clean_date[4:6]}-{clean_date[6:8]}")
    print(f"📂 작업 디렉토리: {daily_dir}")
    print("==================================================================")

    # Step 1: 위키 사료 수집
    print("\n[Step 1] 위키피디아 On this day 사료 수집 중...")
    collect_wiki_events(clean_date)

    # Step 2: 1 킬러 + 2 스피드팩트 deepdive 규격 대본 작성
    print("\n[Step 2] 씬별 사료 검색어 및 AI 고증 프롬프트 포함 대본 집필 중...")
    script_path = generate_killer_script(clean_date)
    with open(script_path, "r", encoding="utf-8") as f:
        script_data = json.load(f)

    # Step 3: 사료 이미지 스마트 소싱 (위키미디어 비전 검증 + Vertex AI Imagen 3.0 고증 복원)
    print("\n[Step 3] 씬별 사료 이미지 수집 및 AI 고증 복원 생성 중...")
    updated_script_data = source_scene_images(script_data, daily_dir)

    # Step 4: Google Cloud Neural2 음성 합성
    print("\n[Step 4] 씬별 Google Cloud Neural2 음성 합성 중...")
    generate_scene_audios(updated_script_data, daily_dir)

    # Step 5: deepdive 규격 마스터피스 렌더링
    print("\n[Step 5] 30fps Ken Burns 모션, 골드 진행선, 자막 플레이트 최종 렌더링 중...")
    final_video_path = render_masterpiece_from_script(daily_dir)

    # Step 6: YouTube Shorts 자동 업로드
    if upload:
        token_path = os.path.join(CONFIG_DIR, "youtube_token.json")
        if not os.path.exists(token_path):
            root_token = os.path.join(os.path.dirname(BASE_DIR), "config", "youtube_token.json")
            if os.path.exists(root_token):
                token_path = root_token

        if os.path.exists(token_path):
            print("\n[Step 6] YouTube Shorts 자동 업로드 연동 중...")
            try:
                from src.uploader import upload_masterpiece_video
                upload_masterpiece_video(final_video_path, script_path, privacy=privacy)
            except Exception as e:
                print(f"⚠️ [YouTube] 업로드 중 오류 발생 (영상 제작은 완료됨): {e}")
        else:
            print(f"\n[Step 6] YouTube 토큰 파일이 없어 업로드를 건너뜁니다 ({token_path}).")

    elapsed = time.time() - start_time
    print("\n" + "==================================================================")
    print(f"🎉 [history_daily 마스터피스 제작 완료!] 총 소요 시간: {elapsed:.1f}초")
    print(f"🎥 최종 완성 영상: {final_video_path}")
    print("==================================================================")
    return final_video_path


def main():
    parser = argparse.ArgumentParser(description="history_daily 신규 마스터피스 쇼츠 파이프라인")
    parser.add_argument("date", nargs="?", default=None, help="대상 날짜 (YYYYMMDD 또는 YYYY-MM-DD)")
    parser.add_argument("--date", dest="opt_date", type=str, default=None, help="대상 날짜 (YYYYMMDD)")
    parser.add_argument("--upload", dest="upload", action="store_true", default=True, help="유튜브 자동 업로드 실행 (기본값: True)")
    parser.add_argument("--no-upload", dest="upload", action="store_false", help="유튜브 자동 업로드 건너뛰기")
    parser.add_argument("--privacy", type=str, default="private", choices=["private", "unlisted", "public"], help="유튜브 공개 상태 (기본값: private)")
    args = parser.parse_args()

    target = args.opt_date or args.date
    run_pipeline(target, upload=args.upload, privacy=args.privacy)


if __name__ == "__main__":
    main()
