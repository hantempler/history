import os
import sys
import json
import re
import time
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.config import GCP_PROJECT_ID, GCP_LOCATION, get_daily_dir

KST = timezone(timedelta(hours=9))

def clean_narration_text(text: str) -> str:
    """TTS 및 자막 불일치를 막기 위해 괄호, 한자 표기, 특수문자 정제"""
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'["\'`“”‘’]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def generate_english_script_from_base(client, base_script_data: dict, clean_date: str) -> dict:
    """한국어 베이스 6씬 대본을 1:1 매핑하여 BBC/넷플릭스 다큐멘터리 급 영문 대본으로 적응 집필."""
    month_names = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    mm = int(clean_date[4:6])
    dd = int(clean_date[6:8])
    month_name = month_names[mm - 1]
    eng_date_str = f"{month_name} {dd}"

    scenes = base_script_data.get("scenes", [])
    scenes_context = []
    for sc in scenes:
        scenes_context.append({
            "scene_number": sc.get("scene_number"),
            "korean_title": sc.get("display_title", ""),
            "korean_script": sc.get("script", ""),
            "image_caption_kr": sc.get("image_caption", ""),
            "image_search_keyword": sc.get("image_search_keyword", "")
        })

    prompt = f"""
    You are a master English documentary writer specializing in BBC/Netflix style 3-minute historical shorts for a global audience (1M+ subscribers).
    Today's historical date is {eng_date_str}.
    
    Below is the curated historical narrative composed of 6 scenes (Scenes 1-4: Killer Main Story, Scenes 5-6: Fascinating Speed Facts):
    {json.dumps(scenes_context, ensure_ascii=False, indent=2)}
    
    [Instructions - BBC/Netflix Quality Global Documentary]:
    1. Hook: Write a shocking, provocative, high-suspense opening question (hook_question) within 15 words.
    2. Scenes 1-4 (Main Story):
       - Scene 1: [Inciting Incident] The rising crisis or tragedy that set the world on edge (40-55 words).
       - Scene 2: [Rising Action] Clashing powers, desperate negotiations, or high-stakes struggle (40-55 words).
       - Scene 3: [Climax] The dramatic tipping point or fateful decision (40-55 words).
       - Scene 4: [Resolution & Legacy] The seismic turning point and butterfly effect on modern history (40-55 words).
    3. Scenes 5-6 (Speed Facts):
       - 25-35 words each. Fascinating, punchy historical facts with surprising details.
    4. [CRITICAL FORMATTING RULES]:
       - ABSOLUTELY NO EMOJIS (No hourglass, scrolls, monuments, etc.).
       - display_title: 3-5 words in ALL UPPERCASE (e.g., 'THE DAWN OF CRISIS', 'FALL OF THE EMPIRE').
       - image_caption: 3-6 words in English describing the historical archive or reconstruction.
    5. outro_debate: An ethical, strategic, or philosophical dilemma for audience debate:
       - badge: "HISTORICAL DILEMMA: PERSPECTIVE A vs B"
       - target_entity: The core historical event or decision (e.g., "The Westphalian Peace of 1648")
       - question_a_1: First line of Perspective A
       - question_a_2: Second line of Perspective A
       - question_b_1: First line of Perspective B
       - question_b_2: Second line of Perspective B
    6. Language & Tone: Use gripping, cinematic, formal documentary English.
    
    [Output JSON Format]:
    {{
        "corner_name": "History Time Machine",
        "event_title": "{base_script_data.get('main_year', '')} {eng_date_str}",
        "main_year": "{base_script_data.get('main_year', '')}",
        "hook_question": "Shocking question?",
        "why_today_title": "Why It Matters Today",
        "why_today_desc": "Profound insight in one sentence",
        "bgm": "{base_script_data.get('bgm', 'ancient_rite.mp3')}",
        "lang": "en",
        "outro_debate": {{
            "badge": "HISTORICAL DILEMMA: PERSPECTIVE A vs B",
            "target_entity": "Event Name",
            "question_a_1": "Perspective A line 1",
            "question_a_2": "Perspective A line 2",
            "question_b_1": "Perspective B line 1",
            "question_b_2": "Perspective B line 2"
        }},
        "scenes": [
            {{
                "scene_number": 1,
                "display_title": "SCENE 1 TITLE",
                "script": "English narration (40-55 words)...",
                "image_search_keyword": "keyword",
                "image_caption": "English archive caption",
                "ai_image_prompt": "Cinematic prompt..."
            }}
        ]
    }}
    """
    res = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.7
        )
    )
    en_data = json.loads(res.text.strip())
    en_data["lang"] = "en"
    en_data["bgm"] = base_script_data.get("bgm", "ancient_rite.mp3")
    en_data["main_year"] = base_script_data.get("main_year", "")

    # base_script_data의 이미지 메타데이터(크레딧, 타입, 프롬프트) 병합
    base_scenes_map = {sc.get("scene_number", idx + 1): sc for idx, sc in enumerate(scenes)}
    for idx, sc in enumerate(en_data.get("scenes", [])):
        s_num = sc.get("scene_number", idx + 1)
        base_sc = base_scenes_map.get(s_num, {})
        sc["script"] = clean_narration_text(sc.get("script", ""))
        sc["image_type"] = base_sc.get("image_type", "archive")
        sc["image_search_keyword"] = base_sc.get("image_search_keyword", sc.get("image_search_keyword", ""))
        sc["ai_image_prompt"] = base_sc.get("ai_image_prompt", sc.get("ai_image_prompt", ""))
        if not sc.get("image_caption"):
            sc["image_caption"] = base_sc.get("image_caption", "Historical Record")
        if sc.get("image_type") == "ai_generated":
            sc["credit"] = "Visualized by Vertex AI (Historical Reconstruction)"
        else:
            sc["credit"] = "Archive Source: Wikimedia Commons"

    return en_data


def generate_killer_script(target_date=None, edition="history", base_script_data=None):
    client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_LOCATION)
    
    if not target_date:
        target_date = datetime.now(KST).strftime("%Y%m%d")
        
    clean_date = target_date.replace("-", "")
    daily_dir = get_daily_dir(clean_date)
    is_english = edition in ("history_en", "en")

    # 영문 에디션 처리 분기
    if is_english:
        print(f"\n[ScriptGen] 글로벌 영문판(history_en) 대본 생성 시작 (대상: {clean_date})")
        if not base_script_data:
            ko_script_p = os.path.join(get_daily_dir(clean_date, edition="history"), "masterpiece_script.json")
            if not os.path.exists(ko_script_p):
                ko_script_p = os.path.join(daily_dir, "masterpiece_script.json")

            if os.path.exists(ko_script_p):
                with open(ko_script_p, "r", encoding="utf-8") as f:
                    base_script_data = json.load(f)
            else:
                print("  ℹ️ 한국어 베이스 대본이 없어 한국어 큐레이션 먼저 수행 후 영문화합니다...")
                generate_killer_script(clean_date, edition="history")
                with open(ko_script_p, "r", encoding="utf-8") as f:
                    base_script_data = json.load(f)

        en_script_data = generate_english_script_from_base(client, base_script_data, clean_date)
        en_out_dir = get_daily_dir(clean_date, edition="history_en")
        output_path = os.path.join(en_out_dir, "masterpiece_script.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(en_script_data, f, ensure_ascii=False, indent=2)
        print(f"✅ [ScriptGen] 글로벌 영문판(history_en) 네이티브 대본 집필 완료: {output_path}")
        return output_path

    # 한국어 에디션 처리 분기
    raw_path = os.path.join(daily_dir, "1_raw_events.json")
    if not os.path.exists(raw_path):
        from src.wiki_collector import collect_wiki_events
        raw_path = collect_wiki_events(target_date)
        if not raw_path or not os.path.exists(raw_path):
            raise FileNotFoundError(f"사료 수집 실패: {raw_path}")
            
    with open(raw_path, "r", encoding="utf-8") as f:
        events = json.load(f)
        
    month = int(clean_date[4:6])
    day = int(clean_date[6:8])
    month_day = f"{month}월 {day}일"
    
    # ── 1. 사건 큐레이션 (메인 1개 심층 서사 + 스피드팩트 1~2개) ──
    print(f"\n[ScriptGen] {month_day} 역사 사건 중 킬러 메인 스토리(집중 조명) & 스피드 팩트 선별 중...")
    
    events_summary = []
    for i, e in enumerate(events):
        has_img = "O" if e.get("image_url") else "X"
        events_summary.append(f"[{i}] ({e['year']}년, 이미지:{has_img}) {e['text']}")
        
    curation_prompt = f"""
    당신은 100만 구독자를 보유한 쇼츠/릴스 전문 역사 채널의 수석 에디터입니다.
    아래는 과거의 '{month_day}'에 발생했던 전 세계 역사적 사건 목록입니다.
    
    시청자가 메인 역사 사건의 전말과 인과관계를 깊이 있게 이해할 수 있도록 다음 기준에 따라 사건을 선정하세요:
    1. [main_index]: 35~40초 동안 4개 씬(도입-전개-위기-반전/결말)으로 충분히 시간과 설명을 할애하여 다룰 '단 1개의 가장 중요한 킬러 사건'
    2. [speed_indices]: 후반부에 4~5초 컷으로 가볍게 분위기를 환기해 줄 '가장 흥미로운 스피드 팩트 1~2개'
    
    사건 목록:
    {chr(10).join(events_summary)}
    
    출력 형식 (JSON):
    {{
        "main_index": 12,
        "speed_indices": [4, 18]
    }}
    """
    
    curation_res = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=curation_prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    
    try:
        curated_meta = json.loads(curation_res.text)
        main_idx = curated_meta["main_index"]
        speed_idxs = curated_meta["speed_indices"][:2]
        if len(speed_idxs) < 1:
            for idx_cand in range(len(events)):
                if idx_cand != main_idx:
                    speed_idxs.append(idx_cand)
                    if len(speed_idxs) >= 2:
                        break
    except Exception as e:
        print(f"[ScriptGen] 큐레이션 파싱 실패, 기본 인덱스 사용: {e}")
        main_idx = 0
        speed_idxs = [1, 2]
        
    main_event = events[main_idx]
    speed_events = [events[i] for i in speed_idxs if 0 <= i < len(events)][:2]
    
    # ── 2. deepdive 정규 규격 씬별 대본 집필 ──
    print(f"\n[ScriptGen] deepdive 규격 (메인 사건 심층 4씬 + 스피드 팩트) 대본 집필 중...")
    
    speed_desc = "\n".join([f"스피드 팩트 {idx+1}: {ev['year']}년 - {ev['text']}" for idx, ev in enumerate(speed_events)])
    
    script_prompt = f"""
    당신은 넷플릭스 다큐멘터리 스타일의 고품격 역사 쇼츠(유튜브 쇼츠 최대 3분 정책 반영, 깊이 있는 80~120초 미니 다큐멘터리) 전문 수석 작가입니다.
    오늘 날짜는 '{month_day}'입니다.
    
    [사료 정보]
    메인 사건: {main_event['year']}년 - {main_event['text']}
    상세 내용: {main_event.get('extract', '')}
    
    {speed_desc}
    
    [작성 규칙 - 유튜브 쇼츠 3분 확대 정책 반영: 여유 있고 깊이 있는 서사 다큐멘터리]
    1. '과거의 오늘엔~' 같은 뻔한 오프닝 절대 금지! 첫 2초 만에 시청자를 사로잡는 충격적인 질문형 훅(hook_question).
    2. 유튜브 쇼츠 기준이 최대 3분으로 대폭 늘어났으므로 60초 시간에 쫓기듯 단편적인 사실만 나열하지 말고, 충분한 호흡과 깊이 있는 인과관계를 담아내십시오:
       - 씬 1: [도입] 운명의 기로와 사건 발단 (발발 배경, 참혹한 전쟁의 비극과 피해, 2~3문장 약 80~100자 내외)
       - 씬 2: [전개] 긴장 고조와 치열한 외교전 (구체적 인물/대립, 피 말리는 협상 과정, 2~3문장 약 80~100자 내외)
       - 씬 3: [위기/절정] 마침내 성사된 역사적 합의 (조약 체결 순간과 극적 합의 과정, 2~3문장 약 80~100자 내외)
       - 씬 4: [반전/영향] 역사적 대전환과 현대적 의의 (주권국가 탄생과 세계사적 나비효과, 2~3문장 약 80~100자 내외)
    3. 스피드 팩트는 씬 5, 씬 6의 2개 씬으로 구성하며, 단순 사실 나열이 아닌 놀라운 디테일을 살려 1~2문장(50~65자 내외)으로 몰입감 있게 작성할 것.
    4. [CRITICAL] 대본, 제목, 캡션, 디베이트 질문 등 모든 텍스트에 이모지(그림 문자: ⏳, 📜, 🏛️, ⚖️ 등)를 절대 포함하지 말 것 (폰트 깨짐 100% 방지).
    5. 각 씬마다 반드시 아래 항목들을 정밀하게 작성할 것:
       - display_title: 상단 헤더에 들어갈 씬별 8~14자의 핵심 소제목 (예: "30년 전쟁의 비극", "열강들의 치열한 외교전", "베스트팔렌 조약 체결")
       - script: 성우가 낭독할 정제되고 깊이 있는 나레이션 (특수기호 없음)
       - image_search_keyword: 위키미디어 Commons에서 실제 역사 사료/사진을 찾기 위한 구체적 영문 검색어
       - image_caption: 화면 사료 태그에 들어갈 10~18자의 한국어 역사 사료 설명 (예: "17세기 종교 전쟁 기록화", "페르디난트 3세 초상화")
       - ai_image_prompt: 위키미디어에 사료가 없을 때 Vertex AI Imagen 3.0으로 생성할 '영문 9:16 시네마틱 역사 고증 일러스트 프롬프트' (Cinematic period chiaroscuro lighting, vertical 9:16 portrait composition, historical realism, 8k resolution, no modern elements, no text)
    6. outro_debate: 메인 사건과 관련하여 시청자가 댓글로 A vs B 선택 투표를 할 수 있는 날카로운 딜레마 카피:
       - target_entity: 사건명/소제목 (예: "1648년 베스트팔렌 조약")
       - question_a_1: 관점 A 첫째 줄 (예: "수백만 희생 끝에 찾아온")
       - question_a_2: 관점 A 둘째 줄 (예: "평화를 위한 위대한 외교적 타협")
       - question_b_1: 관점 B 첫째 줄 (예: "새로운 분쟁의 씨앗이 된")
       - question_b_2: 관점 B 둘째 줄 (예: "미완의 불완전한 합의")
    7. bgm: 사건 분위기에 가장 어울리는 BGM 1종 선택 (반드시 아래 후보 중 1개):
       - "ancient_rite.mp3" (고대사, 사극, 역사적 제의, 진중함)
       - "impact_prelude.mp3" (전쟁, 군사작전, 위기 결전, 긴박감)
       - "darkness_is_coming.mp3" (암살, 음모, 비극, 비장함)
       - "aces_high.mp3" (우주/항공, 과학기술, 도전과 승리)
       - "this_house.mp3" (미스터리, 충격적 비밀, 서스펜스)
       - "clash_defiant.mp3" (혁명, 저항, 세기의 라이벌, 빠른 비트)
       - "cryptic_sorrow.mp3" (대공황, 경제위기, 슬픔과 여운)

    [출력 JSON 포맷]:
    {{
        "corner_name": "역사 타임머신",
        "event_title": "{main_event['year']}년 {main_event['text'][:25]}",
        "main_year": "{main_event['year']}",
        "hook_question": "시청자를 끌어당기는 첫 2초 충격 훅 질문",
        "why_today_title": "오늘 알아야 할 이유",
        "why_today_desc": "역사의 교훈과 통찰 한 줄 설명",
        "bgm": "분위기에 맞는 BGM 파일명 (예: impact_prelude.mp3)",
        "outro_debate": {{
            "badge": "역사의 선택 A vs B",
            "target_entity": "사건명/소제목 1줄",
            "question_a_1": "관점 A 1줄 (예: 수백만 희생 끝에 찾아온)",
            "question_a_2": "관점 A 2줄 (예: 평화를 위한 위대한 외교적 타협)",
            "question_b_1": "관점 B 1줄 (예: 새로운 분쟁의 씨앗이 된)",
            "question_b_2": "관점 B 2줄 (예: 미완의 불완전한 합의)"
        }},
        "scenes": [
            {{
                "scene_number": 1,
                "display_title": "30년 전쟁의 비극",
                "script": "상황 설정 및 발단 나레이션 (2~3문장, 75~95자 내외)",
                "image_search_keyword": "사건 도입부 영문 검색어",
                "image_caption": "17세기 종교 전쟁 기록화",
                "ai_image_prompt": "Cinematic 9:16 illustration prompt for scene 1"
            }},
            {{
                "scene_number": 2,
                "display_title": "열강들의 치열한 외교전",
                "script": "전개 및 충돌 직전 나레이션 (2~3문장, 75~95자 내외)",
                "image_search_keyword": "사건 전개 영문 검색어",
                "image_caption": "페르디난트 3세 초상화",
                "ai_image_prompt": "Cinematic 9:16 illustration prompt for scene 2"
            }},
            {{
                "scene_number": 3,
                "display_title": "베스트팔렌 조약 체결",
                "script": "위기 절정 및 결전 순간 나레이션 (2~3문장, 75~95자 내외)",
                "image_search_keyword": "사건 위기 순간 영문 검색어",
                "image_caption": "1648년 뮌스터 조약 체결식",
                "ai_image_prompt": "Cinematic 9:16 illustration prompt for scene 3"
            }},
            {{
                "scene_number": 4,
                "display_title": "근대 주권국가의 탄생",
                "script": "충격적 결과 및 역사적 나비효과 나레이션 (2~3문장, 75~95자 내외)",
                "image_search_keyword": "사건 결말/반전 영문 검색어",
                "image_caption": "베스트팔렌 조약 후 유럽 지도",
                "ai_image_prompt": "Cinematic 9:16 illustration prompt for scene 4"
            }},
            {{
                "scene_number": 5,
                "display_title": "나이아가라의 기적",
                "script": "스피드 팩트 1 흥미진진한 디테일 나레이션 (1~2문장, 45~60자 내외)",
                "image_search_keyword": "스피드 팩트 1 영문 검색어",
                "image_caption": "스피드 팩트 1 사료 설명",
                "ai_image_prompt": "Cinematic 9:16 illustration prompt for speed fact 1"
            }},
            {{
                "scene_number": 6,
                "display_title": "인류 최초의 지구 촬영",
                "script": "스피드 팩트 2 흥미진진한 디테일 나레이션 (1~2문장, 45~60자 내외)",
                "image_search_keyword": "스피드 팩트 2 영문 검색어",
                "image_caption": "스피드 팩트 2 사료 설명",
                "ai_image_prompt": "Cinematic 9:16 illustration prompt for speed fact 2"
            }}
        ]
    }}
    """
    
    script_res = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=script_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.7
        )
    )
    
    script_data = json.loads(script_res.text.strip())
    script_data["lang"] = "ko"
    
    # 텍스트 클리닝 (특수기호 제거)
    for sc in script_data.get("scenes", []):
        sc["script"] = clean_narration_text(sc.get("script", ""))

    # BGM 다양성 보장 (날짜별 고유 BGM 검증)
    bgm_candidates = [
        "impact_prelude.mp3", "darkness_is_coming.mp3", "aces_high.mp3",
        "ancient_rite.mp3", "clash_defiant.mp3", "this_house.mp3", "cryptic_sorrow.mp3"
    ]
    cur_bgm = script_data.get("bgm", "")
    if cur_bgm not in bgm_candidates:
        try:
            dt_obj = datetime.strptime(clean_date, "%Y%m%d")
            script_data["bgm"] = bgm_candidates[dt_obj.weekday() % len(bgm_candidates)]
        except Exception:
            script_data["bgm"] = bgm_candidates[0]

    # 한국어 전용 디렉토리 및 공통 루트에 저장
    ko_dir = get_daily_dir(clean_date, edition="history")
    output_path = os.path.join(ko_dir, "masterpiece_script.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)

    # 하위 호환성을 위해 공통 루트에도 동기화
    root_script_path = os.path.join(daily_dir, "masterpiece_script.json")
    with open(root_script_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)
        
    print(f"✅ [ScriptGen] 한국어 deepdive 규격 대본 작성 완료: {output_path}")
    return output_path

if __name__ == "__main__":
    generate_killer_script()

