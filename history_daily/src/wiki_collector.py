import os
import json
import urllib.request
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.config import get_daily_dir

def collect_wiki_events(target_date=None):
    if not target_date:
        target_date = datetime.now().strftime("%Y%m%d")
        
    daily_dir = get_daily_dir(target_date)
    os.makedirs(daily_dir, exist_ok=True)
    
    clean_date = target_date.replace("-", "")
    month = f"{int(clean_date[4:6]):02d}"
    day = f"{int(clean_date[6:8]):02d}"
    
    url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{month}/{day}"
    print(f"[WikiCollector] {month}월 {day}일 역사 사료 수집 시작: {url}")
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'})
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"[WikiCollector] 위키피디아 API 수집 실패: {e}")
        return None
        
    events = data.get('events', [])
    print(f"[WikiCollector] 총 {len(events)}건의 역사 사건 발견.")
    
    processed_events = []
    for evt in events:
        year = evt.get('year', 'Unknown')
        text = evt.get('text', '')
        
        thumbnail_url = None
        highres_url = None
        extract = ""
        pages = evt.get('pages', [])
        
        for page in pages:
            if not extract:
                extract = page.get('extract', '')
            if page.get('originalimage') and page['originalimage'].get('source'):
                highres_url = page['originalimage']['source']
            if page.get('thumbnail') and page['thumbnail'].get('source'):
                thumbnail_url = page['thumbnail']['source']
            if thumbnail_url or highres_url:
                break
                
        processed_events.append({
            "year": str(year),
            "text": text,
            "extract": extract,
            "image_url": highres_url or thumbnail_url,
            "thumbnail_url": thumbnail_url
        })
        
    output_path = os.path.join(daily_dir, "1_raw_events.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(processed_events, f, ensure_ascii=False, indent=2)
        
    print(f"[WikiCollector] {len(processed_events)}개 사료 저장 완료: {output_path}")
    return output_path

if __name__ == "__main__":
    collect_wiki_events()
