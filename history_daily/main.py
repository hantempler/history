import os
import sys
from datetime import datetime
import inquirer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from auto_run import run_pipeline


def main():
    print("=== [history_daily] 신규 1킬러+2스피드팩트 쇼츠 마스터피스 엔진 ===")
    questions = [
        inquirer.List(
            'date_option',
            message="어느 날짜의 사건으로 쇼츠를 제작하시겠습니까?",
            choices=['오늘 (KST 기본값)', '직접 날짜 입력 (YYYYMMDD)'],
        ),
        inquirer.List(
            'upload_option',
            message="유튜브 자동 업로드를 진행하시겠습니까?",
            choices=[
                '업로드 (비공개 private 모드 - 스튜디오 확인 권장)',
                '업로드 (공개 public 모드)',
                '업로드 안 함 (로컬 렌더링만 수행)'
            ],
        )
    ]
    answers = inquirer.prompt(questions)
    if not answers:
        return

    target_date = datetime.now().strftime("%Y%m%d")
    if answers['date_option'] == '직접 날짜 입력 (YYYYMMDD)':
        date_q = [
            inquirer.Text('custom_date', message="날짜를 8자리 숫자로 입력하세요 (예: 20261025)")
        ]
        date_a = inquirer.prompt(date_q)
        if not date_a or not date_a['custom_date'].strip():
            return
        target_date = date_a['custom_date'].strip()

    upload = True
    privacy = "private"
    if '안 함' in answers['upload_option']:
        upload = False
    elif '공개' in answers['upload_option']:
        privacy = "public"

    run_pipeline(target_date, upload=upload, privacy=privacy)


if __name__ == "__main__":
    main()
