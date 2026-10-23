import os
import sys
from datetime import datetime
import inquirer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from auto_run_test import run_test_pipeline

def main():
    print("=== [test_history] 신규 1킬러+2스피드팩트 쇼츠 테스트 엔진 ===")
    questions = [
        inquirer.List('date_option',
                      message="어느 날짜의 사건으로 쇼츠를 제작하시겠습니까?",
                      choices=['오늘 (KST 기본값)', '직접 날짜 입력 (YYYYMMDD)'],
                  ),
    ]
    answers = inquirer.prompt(questions)
    if not answers:
        return
        
    target_date = datetime.now().strftime("%Y%m%d")
    if answers['date_option'] == '직접 날짜 입력 (YYYYMMDD)':
        date_q = [
            inquirer.Text('custom_date', message="날짜를 8자리 숫자로 입력하세요 (예: 20261023)")
        ]
        date_a = inquirer.prompt(date_q)
        if not date_a or not date_a['custom_date'].strip():
            return
        target_date = date_a['custom_date'].strip()
        
    run_test_pipeline(target_date)

if __name__ == "__main__":
    main()
