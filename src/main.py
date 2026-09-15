import os
import sys
import inquirer
from datetime import datetime

# Add src to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.scraper import scrape_naver_ranking_news
from src.script_gen import run_script_gen
from src.tts_gen import run_tts_gen
from src.renderer_1_thumb import run_renderer_thumb
from src.renderer_2_video import run_renderer_video

def main():
    print("=== 뉴스 브리핑 자동화 파이프라인 (V2) ===")
    questions = [
        inquirer.List('edition',
                      message="어느 버전을 실행하시겠습니까?",
                      choices=[
                          'morning (출근길 뉴스)',
                          'lunch (점심시간 뉴스)',
                          'evening (퇴근길 뉴스)',
                          'weekend_morning (주말 아침 라이프)',
                          'weekend_evening (주말 저녁 라이프)',
                      ],
                  ),
        inquirer.List('date_option',
                      message="어느 날짜의 기사를 수집/처리하시겠습니까?",
                      choices=['오늘 (기본값)', '직접 입력 (YYYYMMDD)'],
                  ),
    ]
    answers = inquirer.prompt(questions)
    
    if not answers:
        return
        
    if 'weekend_morning' in answers['edition']:
        edition = 'weekend_morning'
    elif 'weekend_evening' in answers['edition']:
        edition = 'weekend_evening'
    elif 'morning' in answers['edition']:
        edition = 'morning'
    elif 'lunch' in answers['edition']:
        edition = 'lunch'
    else:
        edition = 'evening'
    
    target_date = datetime.now().strftime("%Y%m%d")
    if answers['date_option'] == '직접 입력 (YYYYMMDD)':
        date_q = [
            inquirer.Text('custom_date', message="날짜를 입력하세요 (예: 20260908)")
        ]
        date_a = inquirer.prompt(date_q)
        if not date_a:
            return
        target_date = date_a['custom_date']
        
    print(f"\n[{edition.upper()}] 파이프라인 시작 (대상 날짜: {target_date})")
    
    try:
        print("\n--- 1. 기사 스크랩 ---")
        scrape_naver_ranking_news(target_date, edition=edition)
        
        print("\n--- 2. 대본 작성 ---")
        run_script_gen(target_date, edition=edition)
        
        print("\n--- 3. 음성 합성 (TTS) ---")
        run_tts_gen(target_date, edition=edition)
        
        print("\n--- 4. 썸네일 생성 ---")
        run_renderer_thumb(target_date, edition=edition)
        
        print("\n--- 5. 영상 렌더링 ---")
        run_renderer_video(target_date, edition=edition)
        
        print(f"\n[{edition.upper()}] 모든 작업이 성공적으로 완료되었습니다!")
    except Exception as e:
        print(f"\n작업 중 오류가 발생했습니다: {e}")

if __name__ == "__main__":
    main()
