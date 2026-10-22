import json
import os
import requests
from google import genai
from google.genai import types
from datetime import datetime
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.config import GCP_PROJECT_ID, GCP_LOCATION, get_daily_dir

def run_script_gen(target_date=None, edition='morning'):
    client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_LOCATION)
    
    daily_dir = get_daily_dir(target_date, edition)
    titles_path = os.path.join(daily_dir, "1_all_titles.json")
    if not os.path.exists(titles_path):
        print(f"File not found: {titles_path}. Run wiki_scraper first.")
        return None
        
    with open(titles_path, "r", encoding="utf-8") as f:
        all_events = json.load(f)
        
    if not all_events:
        print("No events available.")
        return None
        
    print(f"Loaded {len(all_events)} historical events.")
    
    # KST 기준 날짜/요일 계산
    if not target_date:
        from datetime import timezone, timedelta
        target_date = datetime.now(timezone(timedelta(hours=9))).strftime("%Y%m%d")
    month_day = f"{int(target_date[4:6])}월 {int(target_date[6:8])}일"
    
    # 1차: 가장 흥미로운 6개 선정 (이미지 없는 경우 대비)
    titles_list_str = ""
    for i, evt in enumerate(all_events):
        titles_list_str += f"[{i}] {evt['year']} - {evt['text']}\n"
        
    selection_prompt = f"""
    아래는 과거의 '오늘({month_day})'에 발생했던 전 세계의 역사적 사건들입니다 (영어).
    이 중에서 한국 유튜브 시청자들이 가장 흥미로워할 만한 사건 6가지를 우선순위대로 골라주세요.
    
    [선정 기준]
    1. (최우선순위 1~2개) 최근의 시류, 현대 사회의 주요 이슈(예: 경제, 갈등, 기술, 국제 정세 등)와 맞닿아 있어서 오늘날의 시청자들에게 깊은 '인사이트'나 교훈을 줄 수 있는 사건을 반드시 1개 이상 포함하세요.
    2. (나머지) 스토리가 극적이거나 대중적으로 인지도가 높아 흥미를 끄는 사건.
    
    선정한 사건의 인덱스 번호를 JSON 배열 형태(예: [12, 45, 10, 5, 8, 90])로만 출력해주세요.
    
    사건 목록:
    {titles_list_str}
    """
    
    selection_response = client.models.generate_content(
        model='gemini-2.5-pro',
        contents=selection_prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    
    try:
        selected_indices = json.loads(selection_response.text)
    except Exception:
        selected_indices = [0, 1, 2, 3, 4, 5]
        
    selected_events = []
    issue_counter = 1
    
    for idx in selected_indices:
        if len(selected_events) >= 3:
            break
        if 0 <= idx < len(all_events):
            evt = all_events[idx]
            # 썸네일 다운로드
            img_path = None
            if evt.get('thumbnail_url'):
                try:
                    img_res = requests.get(evt['thumbnail_url'], headers={"User-Agent": "Mozilla/5.0"})
                    if img_res.status_code == 200:
                        img_filename = f"2_img_issue{issue_counter}.jpg"
                        img_path = os.path.join(daily_dir, img_filename)
                        with open(img_path, "wb") as img_f:
                            img_f.write(img_res.content)
                except Exception as e:
                    print(f"Failed to download image for {evt['year']}: {e}")
                    
            if not img_path:
                print(f"Skipping index {idx} due to missing image.")
                continue
                
            evt['image_path'] = img_path
            selected_events.append(evt)
            issue_counter += 1
            
    # 선택된 기사 저장
    selected_path = os.path.join(daily_dir, "2_selected_articles.json")
    with open(selected_path, "w", encoding="utf-8") as f:
        json.dump(selected_events, f, ensure_ascii=False, indent=2)
        
    # 2차: 대본 작성 (다큐멘터리 톤)
    context = ""
    for i, evt in enumerate(selected_events):
        context += f"이슈 {i+1} (연도: {evt['year']}):\n요약: {evt['text']}\n상세: {evt['extract']}\n\n"
        
    if edition == 'history_en':
        dt = datetime.strptime(target_date, '%Y%m%d')
        month_day_en = f"{dt.strftime('%B')} {dt.day}"
        system_instruction = (
            "You are the main narrator and scriptwriter for an immersive YouTube history documentary channel targeting a global audience.\n"
            f"Today's date is '{month_day_en}'. Write the script in perfect, captivating English.\n"
            "Use a dramatic, engaging tone similar to a movie trailer, while maintaining historical credibility."
        )
        script_prompt = f"""
        Based on the following 3 historical events that happened on '{month_day_en}' in the past, write a 1-minute YouTube Shorts script.
        
        Conditions:
        1. Output MUST be in JSON format only.
        2. Output ONLY the narration text (no stage directions).
        3. For at least one of the 3 events, explicitly connect it to current modern trends or issues to provide a poignant insight for today's audience.
        
        Output Format (JSON):
        {{
            "hook_title": "A short, impactful title hook connecting the 3 events (max 5 words, e.g., 3 Events that Changed {month_day_en})",
            "hook": "On this day, {month_day_en}, what happened in history? Let's dive into 3 events that changed the world.",
            "issue1_title": "(Short, catchy title for event 1, max 5 words)",
            "issue1": "(Dramatic and engaging narration for event 1, 3-4 sentences)",
            "issue2_title": "(Short, catchy title for event 2, max 5 words)",
            "issue2": "(Dramatic and engaging narration for event 2, 3-4 sentences)",
            "issue3_title": "(Short, catchy title for event 3, max 5 words)",
            "issue3": "(Dramatic and engaging narration for event 3, 3-4 sentences)",
            "closing": "(A deep insight or historical lesson connecting today's 3 events, 3-4 sentences)",
            "closing_quote": "(A profound quote or one-line insight piercing through today's events) - (Speaker or '1 Min Time Machine')\\n\\nPlease subscribe and like!"
        }}
        
        Issue Data:
        {context}
        """
    else:
        system_instruction = (
            "당신은 몰입감 넘치는 유튜브 역사 다큐멘터리 채널의 메인 내레이터이자 대본 작가입니다.\n"
            f"오늘의 날짜는 '{month_day}'입니다. 대본을 완벽한 한국어로 번역/각색하여 작성하세요.\n"
            "말투는 신뢰감 있으면서도 영화 예고편처럼 사람들을 빠져들게 하는 극적인 어투를 사용하세요."
        )
        
        script_prompt = f"""
        과거의 '{month_day}'에 발생했던 아래 3가지 역사적 사건을 바탕으로 1분 분량의 쇼츠 대본을 작성해주세요.
        
        조건:
        1. 대본은 반드시 JSON 형식으로 출력
        2. 나레이션 텍스트만 출력할 것 (지시문 금지)
        3. 세 가지 사건 중 최소 한 가지는 현재의 시대상이나 최신 시류와 연결하여 현대인에게 주는 시사점이나 인사이트를 내레이션에 명시적으로 포함할 것.
        
        출력 형식 (JSON):
        {{
            "hook_title": "오늘의 3가지 사건을 관통하는 15자 내외의 강렬한 자막 훅 (예: 세상을 바꾼 {month_day}의 3가지 사건)",
            "hook": "{month_day}, 과거의 오늘엔 어떤 일이 있었을까요? 세상을 바꾼 3가지 사건을 만나봅니다.",
            "issue1_title": "(첫 번째 사건의 화면 노출용 15자 내외 한국어 요약 제목)",
            "issue1": "(첫 번째 사건에 대한 극적이고 흥미로운 한국어 나레이션, 3-4문장)",
            "issue2_title": "(두 번째 사건의 화면 노출용 15자 내외 한국어 요약 제목)",
            "issue2": "(두 번째 사건에 대한 극적이고 흥미로운 한국어 나레이션, 3-4문장)",
            "issue3_title": "(세 번째 사건의 화면 노출용 15자 내외 한국어 요약 제목)",
            "issue3": "(세 번째 사건에 대한 극적이고 흥미로운 한국어 나레이션, 3-4문장)",
            "closing": "(오늘 소개된 3가지 역사적 사건들을 관통하는 깊이 있는 인사이트나 역사적 교훈을 담은 내레이션, 3-4문장)",
            "closing_quote": "(오늘의 사건들을 꿰뚫는 짧은 한 줄 통찰 또는 명언) - (발언자 혹은 '1분 타임머신')\\n\\n구독과 좋아요 부탁드립니다!"
        }}
        
        이슈 데이터:
        {context}
        """
    
    response = client.models.generate_content(
        model='gemini-2.5-pro',
        contents=script_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
        )
    )
    
    script_text = response.text.strip()
    
    raw_output_path = os.path.join(daily_dir, "3_script_raw.json")
    with open(raw_output_path, "w", encoding="utf-8") as f:
        f.write(script_text)
        
    print(f"Generated raw script saved to {raw_output_path}")
    
    print("Running fact-check...")
    if edition == 'history_en':
        fact_check_instruction = (
            "You are a meticulous history fact-checker. Please review the provided JSON script generated for a YouTube shorts video. "
            "Compare it against established historical facts.\n"
            "If there are any hallucinations, exaggerated claims, or historical inaccuracies, correct them in the script. "
            "Ensure the tone remains dramatic and engaging, and the format strictly adheres to the original JSON schema.\n"
            "Output ONLY the fact-checked and corrected JSON without any other commentary."
        )
    else:
        fact_check_instruction = (
            "당신은 엄격한 역사 팩트체커(Fact-Checker)입니다. 다음 생성된 JSON 대본을 읽고 역사적 사실과 교차 검증하세요.\n"
            "만약 역사적 사실과 다르거나, 과장되거나, 불확실한 야사가 사실처럼 단정된 부분이 있다면 정사(正史)에 맞게 대본을 수정하세요.\n"
            "극적인 다큐멘터리 톤은 유지해야 하며, 반드시 원본과 동일한 JSON 포맷으로만 출력하세요. 다른 설명은 붙이지 마세요."
        )
        
    fact_check_response = client.models.generate_content(
        model='gemini-2.5-pro',
        contents=script_text,
        config=types.GenerateContentConfig(
            system_instruction=fact_check_instruction,
            response_mime_type="application/json",
        )
    )
    
    final_script_text = fact_check_response.text.strip()
    
    output_path = os.path.join(daily_dir, "3_script.json")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_script_text)
        
    print(f"Fact-checked script saved to {output_path}")
    return final_script_text

if __name__ == "__main__":
    run_script_gen()
