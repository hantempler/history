"""history_daily 사료 메타데이터 1차 압축 수집기 (src/wiki_collector.py).
하드코딩 키워드 매칭을 전면 폐지하고,
사료의 구조적 신호(실록 사관평 史臣曰, 위키 핵심 사건)를 기반으로
당일(MM-DD) 위키피디아(20건)와 조선왕조실록(10건)을 '1줄 요약 메타데이터'로 압축 수집하여
총 30건의 정예 사료 후보를 '1_raw_events.json'으로 저장합니다.
"""
import os
import sys
import json
import sqlite3
import requests
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

# 콘솔 인코딩 방어
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(BASE_DIR)
sys.path.append(BASE_DIR)
from src.config import get_daily_dir

KST = timezone(timedelta(hours=9))


def get_sillok_db_path() -> Optional[str]:
    """로컬 내 실록 DB 파일 경로 탐색"""
    candidates = [
        os.path.join(ROOT_DIR, "history_deepdive", "data", "sillok.db"),
        os.path.join(BASE_DIR, "data", "sillok.db"),
        os.path.join(ROOT_DIR, "history_josun", "data", "sillok.db")
    ]
    for path in candidates:
        if os.path.exists(path) and os.path.getsize(path) > 10 * 1024 * 1024:
            return path
    return None


def collect_sillok_metadata(month_str: str, day_str: str, limit: int = 10) -> List[Dict[str, Any]]:
    """조선왕조실록 DB에서 사관평(史臣曰) 보유 기사를 최우선으로 1줄 요약 메타데이터 추출 (기본 10건)"""
    db_path = get_sillok_db_path()
    if not db_path:
        print("  ⚠️ [실록 DB 경고] sillok.db를 찾을 수 없습니다.")
        return []

    month = f"{int(month_str):02d}"
    day = f"{int(day_str):02d}"
    date_pattern = f"%-{month}-{day}"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    sql = """
    SELECT article_id, king_code, king_name, regnal_year, solar_date, lunar_date,
           title, content_han, has_sasin, sasin_text
    FROM articles
    WHERE solar_date LIKE ?
    ORDER BY has_sasin DESC, LENGTH(content_han) DESC
    LIMIT ?
    """
    rows = cursor.execute(sql, (date_pattern, limit)).fetchall()
    conn.close()

    metadata_list = []
    for r in rows:
        king = (r["king_name"] or "").strip()
        year = (r["solar_date"] or "")[:4] or str(r["regnal_year"] or "")
        title = (r["title"] or "").strip()
        has_sasin = bool(r["has_sasin"])
        sasin_raw = (r["sasin_text"] or "").strip()
        content_raw = (r["content_han"] or "").strip()

        sasin_snippet = sasin_raw.replace("\n", " ")[:120].strip() if sasin_raw else ""
        content_snippet = content_raw.replace("\n", " ")[:120].strip() if content_raw else ""

        one_liner = f"[{king}실록] {title}"
        if has_sasin and sasin_snippet:
            one_liner += f" (사관평: {sasin_snippet}...)"

        metadata_list.append({
            "source": "sillok_db",
            "article_id": r["article_id"],
            "year": year,
            "king_name": king,
            "title": title,
            "has_sasin": has_sasin,
            "sasin_snippet": sasin_snippet,
            "one_liner": one_liner,
            "summary": content_snippet
        })

    return metadata_list


def collect_wikipedia_metadata(month_str: str, day_str: str, limit: int = 20) -> List[Dict[str, Any]]:
    """위키피디아 On this day API에서 사건 1줄 요약 메타데이터 추출 (기본 20건)"""
    m = str(int(month_str))
    d = str(int(day_str))
    url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{m}/{d}"

    headers = {'User-Agent': 'PRJHistoryBot/2.0 (history documentary engine; contact: dev@history.local)'}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        data = resp.json()
    except Exception as e:
        print(f"  ⚠️ [위키피디아 경고] API 요청 실패: {e}")
        return []

    raw_events = data.get('events', [])
    metadata_list = []

    for evt in raw_events[:limit]:
        year = str(evt.get('year', 'Unknown'))
        text = evt.get('text', '').strip()

        thumbnail_url = None
        pages = evt.get('pages', [])
        related_pages = [p.get('title') for p in pages if p.get('title')]
        wiki_page_title = related_pages[0] if related_pages else None
        for page in pages:
            if page.get('thumbnail') and page['thumbnail'].get('source'):
                thumbnail_url = page['thumbnail']['source']
                break

        metadata_list.append({
            "source": "wikipedia",
            "year": year,
            "title": text,
            "one_liner": f"[{year}년] {text}",
            "thumbnail_url": thumbnail_url,
            "wiki_page_title": wiki_page_title,
            "related_wiki_pages": related_pages
        })

    return metadata_list


def collect_wiki_events(target_date: Optional[str] = None) -> Optional[str]:
    """당일 날짜의 위키(20건) + 실록(10건) 메타데이터를 압축 수집하여 1_raw_events.json(총 30건)으로 저장합니다."""
    if not target_date:
        target_date = datetime.now(KST).strftime("%Y%m%d")

    clean_date = target_date.replace("-", "")
    daily_dir = get_daily_dir(clean_date)
    os.makedirs(daily_dir, exist_ok=True)

    month = f"{int(clean_date[4:6]):02d}"
    day = f"{int(clean_date[6:8]):02d}"
    date_display = f"{month}월 {day}일"

    print(f"==================================================================")
    print(f"📑 [사료 메타데이터 압축 수집] {date_display}")
    print(f"==================================================================")

    # 1. 위키피디아 메타데이터 (20건)
    wiki_meta = collect_wikipedia_metadata(month, day, limit=20)
    print(f"  🌐 [위키피디아] 1줄 요약 메타데이터 {len(wiki_meta)}건 추출")

    # 2. 실록 사관평 우선 메타데이터 (10건)
    sillok_meta = collect_sillok_metadata(month, day, limit=10)
    sasin_cnt = sum(1 for s in sillok_meta if s["has_sasin"])
    print(f"  📜 [조선왕조실록] 정사 메타데이터 {len(sillok_meta)}건 추출 (사관 직필평: {sasin_cnt}건)")

    # 3. 통합 정예 메타데이터 리스트 조립 (총 30건)
    combined = []
    for s in sillok_meta:
        combined.append({
            "source": "sillok_db",
            "article_id": s["article_id"],
            "year": s["year"],
            "text": s["one_liner"],
            "extract": s["sasin_snippet"] or s["summary"],
            "has_sasin": s["has_sasin"],
            "image_url": None,
            "thumbnail_url": None
        })

    for w in wiki_meta:
        combined.append({
            "source": "wikipedia",
            "year": w["year"],
            "text": w["title"],
            "extract": w["title"],
            "has_sasin": False,
            "image_url": w.get("thumbnail_url"),
            "thumbnail_url": w.get("thumbnail_url"),
            "wiki_page_title": w.get("wiki_page_title"),
            "related_wiki_pages": w.get("related_wiki_pages", [])
        })

    # 4. 저장 (1_raw_events.json)
    output_path = os.path.join(daily_dir, "1_raw_events.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    print(f"==================================================================")
    print(f"  💾 [수집 완료] 총 {len(combined)}건 (실록 {len(sillok_meta)}건 + 위키 {len(wiki_meta)}건)")
    print(f"  📁 저장 경로: {output_path}")
    print(f"==================================================================\n")

    return output_path


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "20261121"
    collect_wiki_events(target)
