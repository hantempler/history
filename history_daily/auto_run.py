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


def run_pipeline(target_date_str=None, upload=True, privacy="private", edition="all"):
    start_time = time.time()

    if not target_date_str:
        now_kst = datetime.now(KST)
        target_date_str = now_kst.strftime("%Y%m%d")

    clean_date = target_date_str.replace("-", "")
    common_dir = get_daily_dir(clean_date)

    print("==================================================================")
    print(f"🎬 [history_daily 마스터피스 프로덕션 파이프라인 가동]")
    print(f"📅 대상 날짜 (KST): {clean_date[:4]}-{clean_date[4:6]}-{clean_date[6:8]}")
    print(f"📂 공통 작업 디렉토리: {common_dir}")
    print(f"🌐 실행 에디션 모드: {edition.upper()}")
    print("==================================================================")

    # Step 1: 공통 위키 사료 수집
    print("\n[Step 1] 위키피디아 On this day 사료 수집 중...")
    collect_wiki_events(clean_date)

    # Step 2: 6씬 대본 집필 (한국어 기준 사건 큐레이션 및 6씬 확정)
    print("\n[Step 2] 씬별 사료 검색어 및 AI 고증 프롬프트 포함 6씬 대본 집필 중...")
    ko_dir = get_daily_dir(clean_date, edition="history")
    ko_script_path = generate_killer_script(clean_date, edition="history")
    with open(ko_script_path, "r", encoding="utf-8") as f:
        ko_script_data = json.load(f)

    # Step 3: 공통 사료 이미지 스마트 소싱 (위키미디어 검증 + Vertex AI Imagen 3.0 복원, data/{date}/images)
    print("\n[Step 3] 공통 씬별 사료 이미지 수집 및 AI 고증 복원 생성 중...")
    updated_script_data = source_scene_images(ko_script_data, common_dir)
    # 갱신된 메타데이터를 한국어 디렉토리에도 동기화
    with open(ko_script_path, "w", encoding="utf-8") as f:
        json.dump(updated_script_data, f, ensure_ascii=False, indent=2)

    results = {}
    token_path = os.path.join(CONFIG_DIR, "youtube_token.json")
    if not os.path.exists(token_path):
        root_token = os.path.join(os.path.dirname(BASE_DIR), "config", "youtube_token.json")
        if os.path.exists(root_token):
            token_path = root_token

    # ────────────────────────────────────────────────────────────────
    # [에디션 1] 한국어 쇼츠 파이프라인 (history)
    # ────────────────────────────────────────────────────────────────
    if edition in ("all", "history"):
        print("\n" + "="*66)
        print("🇰🇷 [한국어 에디션 (history) 제작 시작]")
        print("="*66)
        try:
            print("\n  [KO-Step 4] 한국어 Google Cloud Neural2 (ko-KR-Neural2-C) 음성 합성 중...")
            generate_scene_audios(updated_script_data, ko_dir, edition="history")

            print("\n  [KO-Step 5] 한국어 30fps Ken Burns 모션, 골드 헤더, 자막 렌더링 중...")
            final_ko_video = render_masterpiece_from_script(ko_dir, lang="ko")
            results["history"] = final_ko_video

            if upload:
                if os.path.exists(token_path):
                    print("\n  [KO-Step 6] 한국어 YouTube Shorts 자동 업로드 연동 중...")
                    from src.uploader import upload_masterpiece_video
                    upload_masterpiece_video(final_ko_video, ko_script_path, privacy=privacy, edition="history")
                else:
                    print(f"\n  [KO-Step 6] YouTube 토큰 파일이 없어 한국어 업로드를 건너뜁니다.")
        except Exception as e:
            print(f"❌ [history] 한국어 파이프라인 오류: {e}")
            if edition == "history":
                raise e

    # ────────────────────────────────────────────────────────────────
    # [에디션 2] 글로벌 영문 쇼츠 파이프라인 (history_en)
    # ────────────────────────────────────────────────────────────────
    if edition in ("all", "history_en"):
        print("\n" + "="*66)
        print("🌐 [글로벌 영문 에디션 (history_en) 제작 시작]")
        print("="*66)
        try:
            if "history" in results and upload:
                print("  ⏳ [안전 버퍼] 동시 업로드 충돌 방지를 위해 5초간 대기합니다...")
                time.sleep(5)

            en_dir = get_daily_dir(clean_date, edition="history_en")

            print("\n  [EN-Step 2] 동일 6씬 기반 BBC/Netflix 다큐멘터리 급 네이티브 영문 대본 집필 중...")
            en_script_path = generate_killer_script(clean_date, edition="history_en", base_script_data=updated_script_data)
            with open(en_script_path, "r", encoding="utf-8") as f:
                en_script_data = json.load(f)

            print("\n  [EN-Step 4] 글로벌 Google Cloud Neural2 (en-US-Neural2-J) 영문 음성 합성 중...")
            generate_scene_audios(en_script_data, en_dir, edition="history_en")

            print("\n  [EN-Step 5] 영문 OCTOBER 헤더, 네이티브 다이내믹 자막 및 시네마틱 렌더링 중...")
            final_en_video = render_masterpiece_from_script(en_dir, lang="en")
            results["history_en"] = final_en_video

            if upload:
                if os.path.exists(token_path):
                    print("\n  [EN-Step 6] 글로벌 YouTube Shorts (defaultLanguage: en) 자동 업로드 연동 중...")
                    from src.uploader import upload_masterpiece_video
                    upload_masterpiece_video(final_en_video, en_script_path, privacy=privacy, edition="history_en")
                else:
                    print(f"\n  [EN-Step 6] YouTube 토큰 파일이 없어 영문 업로드를 건너뜁니다.")
        except Exception as e:
            print(f"⚠️ [history_en] 영문판 처리 중 오류 발생 (한국어 산출물은 100% 안전 보존): {e}")
            if edition == "history_en":
                raise e

    elapsed = time.time() - start_time
    print("\n" + "==================================================================")
    print(f"🎉 [history_daily 전체 마스터피스 파이프라인 완료!] 총 소요 시간: {elapsed:.1f}초")
    for ed_name, v_path in results.items():
        print(f"  🎬 [{ed_name.upper()}] 완성 영상: {v_path}")
    print("==================================================================")
    return results


def main():
    parser = argparse.ArgumentParser(description="history_daily 신규 마스터피스 쇼츠 파이프라인")
    parser.add_argument("date", nargs="?", default=None, help="대상 날짜 (YYYYMMDD 또는 YYYY-MM-DD)")
    parser.add_argument("--date", dest="opt_date", type=str, default=None, help="대상 날짜 (YYYYMMDD)")
    parser.add_argument("--edition", type=str, default="all", choices=["all", "history", "history_en"], help="실행할 에디션 (all, history, history_en)")
    parser.add_argument("--upload", dest="upload", action="store_true", default=True, help="유튜브 자동 업로드 실행 (기본값: True)")
    parser.add_argument("--no-upload", dest="upload", action="store_false", help="유튜브 자동 업로드 건너뛰기")
    parser.add_argument("--privacy", type=str, default="private", choices=["private", "unlisted", "public"], help="유튜브 공개 상태 (기본값: private)")
    args = parser.parse_args()

    target = args.opt_date or args.date
    run_pipeline(target, upload=args.upload, privacy=args.privacy, edition=args.edition)


if __name__ == "__main__":
    main()
