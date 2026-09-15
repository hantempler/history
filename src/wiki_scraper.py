import os
import json
import urllib.request
import sys
from datetime import datetime

# Add src to Python path if run standalone
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.config import get_daily_dir

def scrape_wiki_onthisday(target_date=None, edition='morning'):
    if not target_date:
        target_date = datetime.now().strftime("%Y%m%d")
        
    daily_dir = get_daily_dir(target_date, edition)
    os.makedirs(daily_dir, exist_ok=True)
    
    month = target_date[4:6]
    day = target_date[6:8]
    
    url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{month}/{day}"
    print(f"[Scraper] Fetching events for {month}/{day} from {url}")
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"[Scraper] Error fetching Wikipedia API: {e}")
        return None
        
    events = data.get('events', [])
    print(f"[Scraper] Found {len(events)} events.")
    
    processed_events = []
    for evt in events:
        year = evt.get('year', 'Unknown')
        text = evt.get('text', '')
        
        # 최우선 관련 위키 페이지에서 썸네일과 세부 정보를 추출
        thumbnail_url = None
        extract = ""
        pages = evt.get('pages', [])
        
        # 썸네일이 있는 페이지를 우선적으로 찾음
        for page in pages:
            if not extract:
                extract = page.get('extract', '')
            if page.get('thumbnail') and page['thumbnail'].get('source'):
                thumbnail_url = page['thumbnail']['source']
                break
                
        processed_events.append({
            "year": year,
            "text": text,
            "extract": extract,
            "thumbnail_url": thumbnail_url
        })
        
    # JSON 파일로 저장 (1_all_titles.json 이름 유지하여 호환성 확보)
    output_path = os.path.join(daily_dir, "1_all_titles.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(processed_events, f, ensure_ascii=False, indent=2)
        
    print(f"[Scraper] Saved {len(processed_events)} events to {output_path}")
    return output_path

if __name__ == "__main__":
    scrape_wiki_onthisday()
