import os
import sys
import time
from datetime import datetime, timezone, timedelta

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from src.source_router import route_daily_content
from src.script_generator import generate_masterpiece_script
from src.asset_sourcer import source_scene_images
from src.tts_engine import generate_scene_audios
import render_masterpiece

KST = timezone(timedelta(hours=9))


def run_pipeline(target_date_str: str = None, upload: bool = False, privacy: str = "private") -> str:
    start_time = time.time()

    # 1. 대상 날짜 결정 (기본값: 오늘 KST)
    if not target_date_str:
        now_kst = datetime.now(KST)
        target_date_str = now_kst.strftime("%Y-%m-%d")

    target_dir = os.path.join(BASE_DIR, "data", "history", target_date_str)
    os.makedirs(target_dir, exist_ok=True)

    print("==================================================================")
    print(f"🎬 [역사 딥다이브 마스터피스 완전 무인 자동화 엔진]")
    print(f"📅 대상 날짜 (KST): {target_date_str}")
    print(f"📂 작업 폴더: {target_dir}")
    print("==================================================================")

    # Step 1: 요일별 독립 데이터 소싱 (수요일: 실록 DB 직결 등)
    print("\n[Step 1] 요일별 독립 사료 소싱 라우터 가동...")
    routed_data = route_daily_content(target_date_str)

    # Step 2: 5개 씬 표준 마스터피스 대본 집필
    print("\n[Step 2] 5개 씬 표준 마스터피스 대본 집필 (Gemini 2.5 Pro)...")
    script_data = generate_masterpiece_script(routed_data, target_dir)

    # Step 3: 고화질 사료 이미지 소싱 (1080x1920 세로 풀스크린용)
    print("\n[Step 3] 씬별 고화질 역사 사료 이미지 수집...")
    source_scene_images(script_data, target_dir)

    # Step 4: 요일별 지정 Neural2 음성 합성
    print("\n[Step 4] 요일별 Neural2 씬별 음성 합성...")
    generate_scene_audios(script_data, routed_data["preset"], target_dir)

    # Step 5: 마스터피스 최종 렌더링
    print("\n[Step 5] 1080x1920 세로 풀스크린 마스터피스 렌더링...")
    final_mp4 = render_masterpiece.render_masterpiece_from_script(target_dir)

    dur = render_masterpiece.get_audio_duration(final_mp4)
    size_mb = os.path.getsize(final_mp4) / (1024 * 1024)
    elapsed = time.time() - start_time

    print("\n==================================================================")
    print(f"🎉 [파이프라인 제작 완료] {final_mp4}")
    print(f"  - 재생 시간: {dur:.2f} 초")
    print(f"  - 파일 크기: {size_mb:.2f} MB")
    print(f"  - 총 소요 시간: {elapsed:.1f} 초")
    print("==================================================================")

    # Step 6: 유튜브 자동 업로드 (옵션)
    if upload:
        try:
            from src.uploader import upload_masterpiece_video
            script_path = os.path.join(target_dir, "masterpiece_script.json")
            upload_masterpiece_video(final_mp4, script_path, privacy=privacy)
        except Exception as e:
            print(f"\n⚠️ [YouTube 업로드 경고] 영상 제작은 완료되었으나 업로드 실패: {e}")

    return final_mp4


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="역사 딥다이브 마스터피스 파이프라인")
    parser.add_argument("date", nargs="?", default=None, help="대상 날짜 (YYYY-MM-DD)")
    parser.add_argument("--date", dest="opt_date", type=str, default=None, help="대상 날짜 (YYYY-MM-DD)")
    parser.add_argument("--upload", action="store_true", help="렌더링 완료 후 유튜브 자동 업로드")
    parser.add_argument("--privacy", type=str, default="private", choices=["private", "unlisted", "public"], help="유튜브 공개 범위 (기본: private)")
    args = parser.parse_args()

    target_date = args.opt_date or args.date
    run_pipeline(target_date, upload=args.upload, privacy=args.privacy)
