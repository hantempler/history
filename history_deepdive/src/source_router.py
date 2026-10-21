import os
import sys
import json
import sqlite3
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_DIR = os.path.dirname(BASE_DIR)
SILLOK_DB_PATH = os.path.join(WORKSPACE_DIR, "history_josun", "data", "sillok.db")

# ---------------------------------------------------------------------------
# 1. 요일별 마스터 프리셋 매트릭스 (0: 월 ~ 6: 일)
# ---------------------------------------------------------------------------
WEEKDAY_PRESETS: Dict[int, Dict[str, Any]] = {
    0: {
        "corner": "역사 딥다이브",
        "theme": "세계사를 바꾼 결정적 하루 (전쟁, 조약, 문명의 대전환)",
        "voice": "ko-KR-Neural2-C",
        "speaking_rate": 0.98,
        "pitch": -0.5,
        "bgm": "bgm_history_epic.mp3",
        "color": (229, 169, 60),      # 샴페인 골드
        "category": "세계사 결정적 순간",
        "source_type": "wiki_deepdive"
    },
    1: {
        "corner": "미스터리 파일",
        "theme": "역사 속 풀리지 않은 미제 사건, 비밀 해금 문서, 미스터리",
        "voice": "ko-KR-Neural2-C",
        "speaking_rate": 1.02,
        "pitch": -0.8,
        "bgm": "this_house.mp3",
        "color": (138, 79, 255),      # 딥 바이올렛
        "category": "역사 미스터리 파일",
        "source_type": "wiki_mystery"
    },
    2: {
        "corner": "실록 오늘",
        "theme": "조선왕조실록 및 한국사 정사 속 오늘 날짜의 기록 (왕실 비사, 사관의 직필 史臣曰)",
        "voice": "ko-KR-Neural2-A",
        "speaking_rate": 1.04,
        "pitch": 0.0,
        "bgm": "ancient_rite.mp3",
        "color": (46, 204, 113),       # 단청 비취 그린
        "category": "조선왕조 비밀기록",
        "source_type": "sillok_db"
    },
    3: {
        "corner": "전술·전쟁사",
        "theme": "승패를 가른 전술, 기만술, 첩보전 및 결전의 순간",
        "voice": "ko-KR-Neural2-B",
        "speaking_rate": 1.00,
        "pitch": -0.2,
        "bgm": "impact_prelude.mp3",
        "color": (231, 76, 60),       # 카민 레드
        "category": "전술과 결전의 역사",
        "source_type": "wiki_military"
    },
    4: {
        "corner": "인물 60초",
        "theme": "역사를 뒤흔든 위인/군주의 치명적 결단과 평전 비화",
        "voice": "ko-KR-Neural2-B",
        "speaking_rate": 0.98,
        "pitch": 0.0,
        "bgm": "darkness_is_coming.mp3",
        "color": (243, 156, 18),       # 웜 앰버
        "category": "인물 60초 열전",
        "source_type": "wiki_figure"
    },
    5: {
        "corner": "역사 VS",
        "theme": "역사적 라이벌 영웅, 숙명의 결전 및 국가 간 정면 대결",
        "voice": "ko-KR-Neural2-C",
        "speaking_rate": 1.08,
        "pitch": 0.2,
        "bgm": "clash_defiant.mp3",
        "color": (52, 152, 219),       # 일렉트릭 블루
        "category": "역사 세기의 라이벌",
        "source_type": "wiki_vs"
    },
    6: {
        "corner": "시국 평행이론",
        "theme": "오늘날 시사·경제 이슈와 500년 전 실록/역사의 소름 돋는 평행이론",
        "voice": "ko-KR-Neural2-A",
        "speaking_rate": 1.04,
        "pitch": 0.0,
        "bgm": "cryptic_sorrow.mp3",
        "color": (149, 165, 166),      # 네오 실버
        "category": "시국 평행이론",
        "source_type": "sillok_parallel"
    }
}


# ---------------------------------------------------------------------------
# 2. 조선왕조실록 DB 수집기 (수요일 / 일요일 직결)
# ---------------------------------------------------------------------------
def collect_sillok_events(month_str: str, day_str: str, limit: int = 25) -> List[Dict[str, Any]]:
    if not os.path.exists(SILLOK_DB_PATH):
        raise FileNotFoundError(f"실록 DB 파일을 찾을 수 없습니다: {SILLOK_DB_PATH}")

    month = f"{int(month_str):02d}"
    day = f"{int(day_str):02d}"
    date_pattern = f"%-{month}-{day}"

    conn = sqlite3.connect(SILLOK_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    sql = """
    SELECT article_id, king_code, king_name, regnal_year, solar_date, lunar_date,
           title, subjects, people, content_han, has_sasin, sasin_text
    FROM articles
    WHERE solar_date LIKE ?
    ORDER BY has_sasin DESC, LENGTH(content_han) DESC
    LIMIT ?
    """
    rows = cursor.execute(sql, (date_pattern, limit)).fetchall()
    conn.close()

    events = []
    for r in rows:
        king = r["king_name"].strip() if r["king_name"] else ""
        year = (r["solar_date"] or "")[:4] or str(r["regnal_year"] or "")
        title = r["title"] or ""
        sasin = (r["sasin_text"] or "").strip()
        han = (r["content_han"] or "").strip()
        
        events.append({
            "source": "sillok_db",
            "article_id": r["article_id"],
            "king_name": king,
            "year": year,
            "solar_date": r["solar_date"],
            "lunar_date": r["lunar_date"],
            "title": f"[{king}실록] {title}",
            "summary": title,
            "has_sasin": bool(r["has_sasin"]),
            "sasin_text": sasin,
            "content_han": han[:500] if han else "",
            "subjects": r["subjects"] or "",
            "people": r["people"] or ""
        })

    print(f"  📜 [실록 DB 직결] {month}월 {day}일 기사 {len(events)}건 추출 완료 (사관 평 포함: {sum(1 for e in events if e['has_sasin'])}건)")
    return events


# ---------------------------------------------------------------------------
# 3. 위키피디아 OnThisDay 수집기 (테마별 키워드 스코어링 필터링)
# ---------------------------------------------------------------------------
THEME_KEYWORDS = {
    "wiki_deepdive": ["empire", "battle", "treaty", "revolution", "independence", "war", "discovery", "pope", "king", "conquest"],
    "wiki_mystery": ["unsolved", "disappearance", "mystery", "conspiracy", "secret", "ghost", "alien", "ufo", "death", "incident"],
    "wiki_military": ["battle", "tactics", "siege", "fleet", "army", "general", "defeat", "victory", "invasion", "war"],
    "wiki_figure": ["born", "died", "assassinated", "coronation", "leader", "emperor", "philosopher", "hero", "admiral"],
    "wiki_vs": ["war", "conflict", "rivalry", "duel", "clash", "treaty", "campaign", "civil war", "rebellion"]
}

def collect_wikipedia_themed_events(month_str: str, day_str: str, source_type: str, limit: int = 30) -> List[Dict[str, Any]]:
    m = str(int(month_str))
    d = str(int(day_str))
    url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{m}/{d}"
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"  ⚠️ 위키피디아 API 요청 실패: {e}")
        return []

    events_raw = data.get('events', [])
    keywords = THEME_KEYWORDS.get(source_type, [])

    scored_events = []
    for evt in events_raw:
        year = evt.get('year', '')
        text = evt.get('text', '')
        lower_text = text.lower()
        score = sum(2 for kw in keywords if kw in lower_text)

        thumb = None
        extract = ""
        for p in evt.get('pages', []):
            if not extract:
                extract = p.get('extract', '')
            if p.get('thumbnail') and p['thumbnail'].get('source'):
                thumb = p['thumbnail']['source']
                break

        scored_events.append({
            "source": "wikipedia",
            "score": score,
            "year": str(year),
            "title": text[:60],
            "text": text,
            "extract": extract,
            "thumbnail": thumb
        })

    # 스코어 높은 순 정렬
    scored_events.sort(key=lambda x: x["score"], reverse=True)
    results = scored_events[:limit]
    print(f"  🌐 [위키피디아 테마 수집] {month_str}월 {day_str}일 ({source_type}) {len(results)}건 선별 완료")
    return results


# ---------------------------------------------------------------------------
# 4. 요일별 통합 라우터 진입점
# ---------------------------------------------------------------------------
def route_daily_content(target_date_str: str) -> Dict[str, Any]:
    dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    weekday = dt.weekday()
    preset = WEEKDAY_PRESETS[weekday]

    month_str = f"{dt.month:02d}"
    day_str = f"{dt.day:02d}"
    source_type = preset["source_type"]

    print("==================================================================")
    print(f"🧭 [요일 소스 라우터 가동] {target_date_str} ({dt.strftime('%A')}, {weekday})")
    print(f"  📌 편성 코너: [{preset['corner']}] - {preset['theme']}")
    print(f"  🎙️ 배정 성우: {preset['voice']} (속도: {preset['speaking_rate']}x, 피치: {preset['pitch']})")
    print(f"  🎵 지정 BGM: {preset['bgm']}")
    print("==================================================================")

    events = []
    if source_type in ["sillok_db", "sillok_parallel"]:
        events = collect_sillok_events(month_str, day_str)
        if not events and source_type == "sillok_db":
            # 혹시 당일 기사가 없을 경우 전후 일자 폴백
            print(f"  ⚠️ 당일 실록 기사 부족, 인접 일자 사료 탐색...")
            events = collect_sillok_events(month_str, f"{int(day_str)+1:02d}")
    else:
        events = collect_wikipedia_themed_events(month_str, day_str, source_type)

    return {
        "target_date": target_date_str,
        "weekday": weekday,
        "weekday_name": dt.strftime('%A'),
        "preset": preset,
        "events": events
    }


if __name__ == "__main__":
    test_date = sys.argv[1] if len(sys.argv) > 1 else "2026-10-21"
    res = route_daily_content(test_date)
    print(f"라우팅 결과 코너: {res['preset']['corner']}, 수집 사건 수: {len(res['events'])}")
