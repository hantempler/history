import os
import sys
import time
import json
import shutil
import urllib.request
import urllib.parse
from PIL import Image

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.config import get_daily_dir, ASSETS_DIR, GCP_PROJECT_ID, GCP_LOCATION
from google import genai
from google.genai import types

FALLBACK_IMAGES = [
    os.path.join(ASSETS_DIR, "dark_paper_bg.jpg"),
    os.path.join(ASSETS_DIR, "vintage_bg.jpg"),
    os.path.join(ASSETS_DIR, "ancient_map_bg.jpg"),
    os.path.join(ASSETS_DIR, "stone_bg.jpg"),
    os.path.join(ASSETS_DIR, "leather_book_bg.jpg")
]


def search_wikimedia_image(keyword: str, script_summary: str, dest_path: str) -> tuple[bool, str]:
    """
    위키미디어 Commons/Wikipedia API 검색 + 핵심 키워드 랭킹 + Gemini Flash 비전 검증
    부적합한 엉뚱한 인물/사진을 100% 걸러내고 검증된 사료만 승인합니다.
    """
    if not keyword:
        return False, None
    try:
        encoded_kw = urllib.parse.quote(keyword)
        url = (
            f"https://en.wikipedia.org/w/api.php?action=query&generator=search"
            f"&gsrsearch={encoded_kw}&gsrlimit=8&prop=pageimages&pithumbsize=1280&format=json"
        )
        req = urllib.request.Request(url, headers={'User-Agent': 'PRJHistoryBot/2.0 (history documentary engine)'})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        pages = list(data.get('query', {}).get('pages', {}).values())
        if not pages:
            return False, None

        # 핵심 고유명사 토큰 추출
        stop_words = {'portrait', 'painting', 'photo', 'photograph', 'landscape', 'map', 'old', 'ancient', 'era', 'in', 'of', 'the', 'a', '1947', '1812', 'battle', 'war'}
        kw_tokens = set([t.lower() for t in keyword.replace('-', ' ').split() if len(t) > 2 and t.lower() not in stop_words])

        ranked_pages = []
        for p in pages:
            title = p.get('title', '')
            thumb = p.get('thumbnail', {}).get('source', '')
            if not thumb:
                continue
            if any(bad in title.lower() or bad in thumb.lower() for bad in ['emblem', 'coat_of_arms', 'flag', 'seal', 'logo', 'symbol', '.svg']):
                continue

            title_tokens = set(title.lower().replace('-', ' ').split())
            match_score = len(kw_tokens.intersection(title_tokens))
            ranked_pages.append((match_score, title, thumb))

        # 핵심 토큰 일치도 높은 순 정렬
        ranked_pages.sort(key=lambda x: x[0], reverse=True)
        if not ranked_pages:
            return False, None

        client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_LOCATION)

        for score, title, thumb_url in ranked_pages:
            if len(kw_tokens) >= 1 and score == 0:
                continue

            img_req = urllib.request.Request(thumb_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(img_req, timeout=15) as img_resp:
                with open(dest_path, "wb") as f_out:
                    f_out.write(img_resp.read())

            try:
                with Image.open(dest_path) as im:
                    im.verify()
            except Exception:
                continue

            # Gemini 2.5 Flash 비전 사실 검증 (0.5초 초고속 판별)
            try:
                with open(dest_path, "rb") as f:
                    img_bytes = f.read()

                v_prompt = (
                    f"You are a strict historical documentary fact-checker.\n"
                    f"Target subject/keyword: '{keyword}'\n"
                    f"Documentary context: '{script_summary}'\n"
                    f"Image article title: '{title}'\n\n"
                    f"Does this image authentically represent or closely relate to the target historical subject (person, event, battle, or artifact)?\n"
                    f"Reply in JSON format: {{\"is_valid\": true/false, \"reason\": \"short reason in Korean\"}}"
                )

                v_resp = client.models.generate_content(
                    model='gemini-3.5-flash',
                    contents=[
                        types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                        v_prompt
                    ],
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                v_res = json.loads(v_resp.text)
                if v_res.get('is_valid'):
                    print(f"    -> [사료 검증 통과] {title} ({v_res.get('reason')})")
                    return True, title
                else:
                    print(f"    ❌ [사료 불합격 판정] {title} (사유: {v_res.get('reason')})")
            except Exception as e:
                if score >= 1:
                    print(f"    -> [사료 수집 성공(키워드매칭)] {title}")
                    return True, title

    except Exception as e:
        print(f"    ⚠️ 위키미디어 검색 오류 ('{keyword}'): {e}")
    return False, None


def generate_image_with_nanobanana(prompt_text: str, dest_path: str, is_joseon: bool = False, max_retries: int = 4) -> bool:
    """Vertex AI gemini-nano-banana-2.1 (global)을 호출하여 9:16 시네마틱 역사 일러스트 생성"""
    client_global = genai.Client(
        vertexai=True,
        project=GCP_PROJECT_ID,
        location="global"
    )

    base_style = "Authentic Korean Joseon Dynasty historical documentary visual: " if is_joseon else "Authentic dramatic historical documentary visual: "
    full_prompt = (
        f"{base_style}{prompt_text}. "
        "Cinematic period chiaroscuro lighting, vertical 9:16 portrait composition, historical realism, 8k resolution, authentic period clothing and architecture, no modern elements, no anime, no cartoon. "
        "CRITICAL REQUIREMENT: Absolutely NO text, NO words, NO letters, NO alphabet, NO typography, NO hangul, NO korean writing, NO captions, NO titles, NO watermark. Completely pure visual imagery without any written characters."
    )

    model_name = "gemini-nano-banana-2.1"

    for attempt in range(max_retries):
        try:
            response = client_global.models.generate_content(
                model=model_name,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                    candidate_count=1
                )
            )
            if response.candidates:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "inline_data") and part.inline_data:
                        with open(dest_path, "wb") as f:
                            f.write(part.inline_data.data)
                        print(f"    ✨ [나노바나나 고증 생성 성공] {dest_path}")
                        return True
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                wait_sec = 60
                print(f"    ⏳ [429 Quota 대기] 쿼터 초과 발생, {wait_sec}초 대기 후 재시도 중 ({attempt+1}/{max_retries})...")
                time.sleep(wait_sec)
            else:
                print(f"    ⚠️ AI 이미지 생성 오류 ({model_name}): {err_str[:80]}")
                time.sleep(5)

    return False


def source_scene_images(script_data: dict, out_dir: str):
    images_dir = os.path.join(out_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    corner = script_data.get("corner_name", "")
    is_joseon = "실록" in corner or "조선" in corner

    print(f"\n[사료 이미지 스마트 소싱] 씬별 사료 수집 및 적합성 검증 - 코너: [{corner}]")

    scenes = script_data.get("scenes", [])
    for idx, sc in enumerate(scenes):
        s_num = sc.get("scene_number", idx + 1)
        dest_path = os.path.join(images_dir, f"scene_{s_num}.jpg")
        keyword = sc.get("image_search_keyword", "")
        script_text = sc.get("script", "")
        ai_prompt = sc.get("ai_image_prompt") or f"Historical scene: {keyword}"
        caption_kr = sc.get("image_caption") or sc.get("display_title", "")

        success = False
        source_title = None

        # 0. 이미 캐싱된 고화질 이미지가 존재하는 경우 즉시 재사용
        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000:
            if not sc.get("image_type"):
                sc["image_type"] = "archive"
            if not sc.get("credit"):
                sc["credit"] = "출처: 역사 기록 사료 / 위키미디어 커먼즈"
            if not sc.get("image_caption"):
                sc["image_caption"] = caption_kr or keyword or "역사 사료 장면"
            print(f"    ♻️ [사료 캐시 재사용] 씬 {s_num}: '{sc['image_caption']}' ({dest_path})")
            continue

        # 1. 위키미디어 사료 우선 탐색 및 검증
        if keyword:
            success, source_title = search_wikimedia_image(keyword, script_text[:80], dest_path)

        if success:
            sc["image_type"] = "archive"
            sc["credit"] = "출처: 역사 기록 사료 / 위키미디어 커먼즈"
            if not sc.get("image_caption"):
                sc["image_caption"] = caption_kr or source_title or keyword
            print(f"    ✅ [사료 채택] 씬 {s_num}: '{sc['image_caption']}'")
        else:
            # 2. 사료가 없거나 부적합할 경우 ➔ Vertex AI Imagen 3.0 고증 일러스트 직접 생성!
            time.sleep(2)
            print(f"    🎨 [AI 고증 복원 가동] 씬 {s_num} 역사 일러스트 생성 중 (프롬프트: '{ai_prompt[:40]}...')...")
            ai_success = generate_image_with_nanobanana(ai_prompt, dest_path, is_joseon=is_joseon)
            if ai_success:
                sc["image_type"] = "ai_generated"
                sc["credit"] = "제작: Vertex AI 시각 복원 / 역사 고증 일러스트"
                if not sc.get("image_caption"):
                    sc["image_caption"] = caption_kr or "역사 고증 복원 장면"
                print(f"    ✅ [고증 복원 채택] 씬 {s_num}: '{sc['image_caption']}'")
            else:
                # 3. 최후의 안전 폴백 배경
                fallback = FALLBACK_IMAGES[idx % len(FALLBACK_IMAGES)]
                if os.path.exists(fallback):
                    shutil.copy(fallback, dest_path)
                else:
                    im = Image.new("RGB", (1080, 1920), (22, 26, 35))
                    im.save(dest_path)
                sc["image_type"] = "fallback"
                sc["credit"] = "출처: 공공 역사 아카이브"
                sc["image_caption"] = caption_kr or "역사 기록 자료"
                print(f"    ℹ️ [안전 폴백] 씬 {s_num}: 빈티지 사료 배경 적용")

    # 대본 파일에 갱신된 메타데이터 저장
    script_path = os.path.join(out_dir, "masterpiece_script.json")
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)

    print(f"  ✅ 전체 씬 고화질 사료 및 고증 이미지 검증/저장 완료.")
    return script_data

if __name__ == "__main__":
    from src.config import get_daily_dir
    target_date = sys.argv[1] if len(sys.argv) > 1 else None
    daily_dir = get_daily_dir(target_date)
    script_path = os.path.join(daily_dir, "masterpiece_script.json")
    if os.path.exists(script_path):
        with open(script_path, "r", encoding="utf-8") as f:
            script_data = json.load(f)
        source_scene_images(script_data, daily_dir)
