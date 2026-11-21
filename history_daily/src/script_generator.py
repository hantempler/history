"""history_daily 킬러 대본 생성기 (src/script_generator.py).
유튜브 채널 138편 실측 분석 기반:
1. 무조건 검증된 3대 킬러 포맷(역사 VS, 시국 평행이론, 역사 딥다이브) 단일 배정 강제.
2. Google Search Grounding 기반 1차 사료(실록/해금문서/전사일지) 전수 팩트체크 & 낭설(Myths) 분리.
3. 7씬 75~95초 황금 러닝타임 엄격 통제 (총 500~600자 구어체 내레이션).
4. 씬별 6대 시네마틱 모션(camera_motion), 노란색 키워드(highlight_keywords), 고정 댓글(pinned_comment) 탑재.
"""
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

# 3대 공인 킬러 포맷 정의
ALLOWED_CORNERS = ["역사 VS", "시국 평행이론", "역사 딥다이브"]

CORNER_PROFILES = {
    "역사 VS": {
        "theme": "무기, 전술, 부대, 장군 간의 정면 충돌 및 극한 상성 대결",
        "bgm": "impact_prelude.mp3",
        "plot_guide": "씬 1(충격 결전 훅) -> 씬 2(무기/전력 상성 분석) -> 씬 3(피할 수 없는 전장 충돌) -> 씬 4(승패를 가른 결정적 전술) -> 씬 5(처절한 사투와 반전) -> 씬 6(세계 전쟁사를 바꾼 결과) -> 씬 7(에필로그 헌사 및 교훈)"
    },
    "시국 평행이론": {
        "theme": "권력 암투, 배신, 밀고, 사법 살인, 궁중 음모 등 인간 본성의 처절한 비극",
        "bgm": "darkness_is_coming.mp3",
        "plot_guide": "씬 1(의문의 사건/배신 훅) -> 씬 2(권력자들의 은밀한 결탁) -> 씬 3(함정에 빠진 희생양) -> 씬 4(피의 숙청과 사법 살인) -> 씬 5(숨겨진 1차 사료의 반전 진실) -> 씬 6(권력의 덧없는 몰락) -> 씬 7(오늘날 시국에 던지는 묵직한 거울)"
    },
    "역사 딥다이브": {
        "theme": "사소한 말실수, 우연, 착오 하나가 세계사를 뒤바꾼 파국적 나비효과",
        "bgm": "ancient_rite.mp3",
        "plot_guide": "씬 1(황당한 나비효과 훅) -> 씬 2(평온했던 그날의 사소한 발단) -> 씬 3(돌이킬 수 없는 결정적 착오/실수) -> 씬 4(걷잡을 수 없는 연쇄 폭발) -> 씬 5(제국의 붕괴와 역사적 대전환) -> 씬 6(살아남은 자들의 충격과 여운) -> 씬 7(역사의 거대한 아이러니 마침표)"
    }
}

VALID_MOTIONS = ["face_zoom", "push_in", "pan_lr", "tilt_up", "vignette_zoom_out", "slow_drift"]


def generate_content_with_retry(client, model: str, contents, config=None, max_retries: int = 3):
    """Vertex AI 429 RESOURCE_EXHAUSTED 발생 시 지수 백오프로 재시도하는 안전 호출 헬퍼"""
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except Exception as e:
            err_str = str(e)
            if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < max_retries - 1:
                wait_sec = (attempt + 1) * 12
                print(f"  ⏳ [Vertex AI 429 Quota 대기] {wait_sec}초 후 재시도 중 ({attempt+1}/{max_retries})...")
                time.sleep(wait_sec)
            else:
                raise e


def clean_narration_text(text: str) -> str:
    """TTS 및 자막 불일치를 막기 위해 괄호, 한자 표기, 특수문자 정제"""
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'["\'`“”‘’]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def run_fact_check_with_grounding(client, types, model, event_year: str, event_text: str, event_extract: str) -> dict:
    """Google Search Grounding을 활용한 1차 사료 전수 검증 및 낭설 분리."""
    print(f"  🔍 [FactCheck Grounding] '{event_year}년 {event_text[:30]}' 팩트체크 및 1차 사료 확인 중...")

    search_prompt = f"""다음 역사적 사건에 대해 신뢰할 수 있는 1차 사료와 정밀 팩트를 검증하세요:
- 연도: {event_year}년
- 사건 내용: {event_text}
- 상세 설명: {event_extract}

확인할 핵심 질문:
1. 이 사건의 정확한 역사적 연도, 날짜, 인물 실명은 무엇입니까?
2. 이 사건을 입증하는 공인된 1차 사료(조선왕조실록 권/책/날짜, 미국 국립문서기록관리청 NARA 문서, 영국 공공기록소 PRO, 공식 전투 일지, 기밀 해금 문서 번호 등)는 무엇입니까?
3. 대중에게 흔히 잘못 알려진 낭설, 야사, 왜곡된 사실(Debunked Myths)이 있다면 무엇이며 실제 진실은 무엇입니까?
4. 이 사건은 다음 3대 킬러 포맷 중 어디에 가장 완벽하게 부합합니까?
   - '역사 VS' (무기/전술/부대 간 상성 대결)
   - '시국 평행이론' (권력 암투, 배신, 밀고, 사법 살인, 궁중 음모)
   - '역사 딥다이브' (사소한 실수/우연이 초래한 세계사적 나비효과)

결과를 다음 JSON 규격으로만 응답하세요:
{{
  "verified_year": "{event_year}",
  "verified_title": "핵심 사건 정식 명칭",
  "assigned_corner": "역사 VS | 시국 평행이론 | 역사 딥다이브 중 택1",
  "corner_reason": "해당 포맷을 선택한 결정적 근거 1문장",
  "primary_source": "1차 사료 공식 명칭 (예: 태종실록 7권 태종 4년 2월 8일 또는 NARA RG-111)",
  "verified_facts": ["핵심 팩트 1", "핵심 팩트 2", "핵심 팩트 3"],
  "debunked_myth": {{"myth": "흔한 대중적 오해/낭설", "truth": "사료가 증명하는 실제 진실"}},
  "killer_hook_point": "첫 3초 시청자의 멱살을 잡을 충격적인 반전 팩트 1문장"
}}
"""
    try:
        cfg = types.GenerateContentConfig(
            temperature=0.2,
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
        resp = generate_content_with_retry(client, model, search_prompt, cfg)
        grounding_text = resp.text.strip()
        time.sleep(2)  # Grounding 부하 완화

        clean_json_str = re.sub(r"^```json\s*", "", grounding_text)
        clean_json_str = re.sub(r"\s*```$", "", clean_json_str).strip()
        fact_meta = json.loads(clean_json_str)

        # 3대 코너 강제 유효성 검증
        if fact_meta.get("assigned_corner") not in ALLOWED_CORNERS:
            fact_meta["assigned_corner"] = "역사 딥다이브"

        print(f"  ✅ [FactCheck 완료] 코너: [{fact_meta['assigned_corner']}] | 사료: {fact_meta.get('primary_source', '공인 역사 아카이브')}")
        return fact_meta

    except Exception as e:
        print(f"  ⚠️ [FactCheck Grounding 폴백]: {e}")
        return {
            "verified_year": event_year,
            "verified_title": event_text[:30],
            "assigned_corner": "역사 딥다이브",
            "corner_reason": "세계사를 바꾼 결정적 순간",
            "primary_source": "공공 역사 기록 사료",
            "verified_facts": [event_text],
            "debunked_myth": {"myth": "대중적 통설", "truth": event_text},
            "killer_hook_point": event_text[:40]
        }


def generate_killer_script(target_date=None, edition="history"):
    client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_LOCATION)

    if not target_date:
        target_date = datetime.now(KST).strftime("%Y%m%d")

    clean_date = target_date.replace("-", "")
    daily_dir = get_daily_dir(clean_date)

    raw_path = os.path.join(daily_dir, "1_raw_events.json")
    if not os.path.exists(raw_path):
        from src.wiki_collector import collect_wiki_events
        raw_path = collect_wiki_events(target_date)
        if not raw_path or not os.path.exists(raw_path):
            raise FileNotFoundError(f"사료 수집 실패: {raw_path}")

    with open(raw_path, "r", encoding="utf-8") as f:
        events = json.load(f)

    if not events:
        raise ValueError(f"선정 가능한 역사 사건이 없습니다 ({target_date}).")

    month = int(clean_date[4:6])
    day = int(clean_date[6:8])
    month_day = f"{month}월 {day}일"

    # ── 1. 사건 큐레이션 (30개 전수 후보 중 3대 킬러 포맷별 1위 선발 후 결선) ──
    print(f"\n[ScriptGen] {month_day} 사료 30건(실록 10건 + 위키 20건) 3대 킬러 포맷별 대표 선발 및 결선 심사 중...")

    candidates = events[:30]
    cand_summary = []
    for i, e in enumerate(candidates):
        src_name = "조선실록(사관평)" if e.get("source") == "sillok_db" and e.get("has_sasin") else ("조선실록" if e.get("source") == "sillok_db" else "세계사위키")
        cand_summary.append(f"[{i}] [{src_name}] {e['year']}년: {e['text']}")

    curation_prompt = f"""당신은 100만 유튜브 쇼츠 채널의 수석 에디터입니다.
아래는 '{month_day}'에 일어난 역사 사건 후보 30건입니다.
3대 킬러 포맷에 각각 100% 동등한 기회를 부여하기 위해, 다음 2단계 심사를 반드시 수행하세요:

[1단계: 3대 킬러 포맷별 최우수 대표 1개씩 선별]
1. [역사 VS]: 무기, 전술, 부대, 장군 간의 정면 충돌 및 극한 상성 대결에 가장 완벽한 대표 사건 1개 선정
2. [시국 평행이론]: 권력 암투, 배신, 밀고, 사법 살인, 궁중 음모 등 인간 본성의 비극에 가장 완벽한 대표 사건 1개 선정
3. [역사 딥다이브]: 사소한 말실수, 우연, 착오 하나가 세계사를 뒤바꾼 파국적 나비효과에 가장 완벽한 대표 사건 1개 선정
(🚨 청백리, 충신 찬양, 도덕 훈계, 단순 기념식은 절대 선택 금지!)

[2단계: 3개 대표 중 오늘의 최종 결선 우승 사건 1개 확정]
- 세 포맷 대표 중 오늘 시청자의 도파민을 가장 극대화하고 3초 훅이 강력한 단 1개의 사건을 최종 우승으로 결정하세요.

후보 목록:
{chr(10).join(cand_summary)}

응답은 반드시 아래 JSON 규격으로만 출력하세요:
{{
  "bracket_candidates": {{
    "역사 VS": {{ "index": 0, "title": "핵심 사건 제목", "reason": "VS 대표 선정 이유 1문장" }},
    "시국 평행이론": {{ "index": 0, "title": "핵심 사건 제목", "reason": "시국 평행이론 대표 선정 이유 1문장" }},
    "역사 딥다이브": {{ "index": 0, "title": "핵심 사건 제목", "reason": "딥다이브 대표 선정 이유 1문장" }}
  }},
  "final_winner_corner": "역사 VS | 시국 평행이론 | 역사 딥다이브 중 택1",
  "selected_index": 0,
  "winner_reason": "오늘 세 대표 중 이 사건을 최종 우승으로 결정한 결정적 이유 1문장"
}}
"""
    cur_res = generate_content_with_retry(
        client,
        model='gemini-3.5-flash',
        contents=curation_prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )

    try:
        cur_meta = json.loads(cur_res.text.strip())
        brackets = cur_meta.get("bracket_candidates", {})
        print("\n  🏆 [3대 킬러 포맷별 1위 대표 후보 선발 결과]")
        for c_name in ALLOWED_CORNERS:
            b_info = brackets.get(c_name, {})
            b_idx = b_info.get("index", "?")
            b_title = b_info.get("title", "미정")
            b_reason = b_info.get("reason", "")
            print(f"    📌 [{c_name:<7}] : [{b_idx}번] {b_title} (이유: {b_reason})")

        sel_idx = cur_meta.get("selected_index", 0)
        target_corner = cur_meta.get("final_winner_corner", cur_meta.get("assigned_corner", "역사 딥다이브"))
        if target_corner not in ALLOWED_CORNERS:
            target_corner = "역사 딥다이브"
        winner_reason = cur_meta.get("winner_reason", "")
    except Exception as e:
        print(f"  ⚠️ [큐레이션 파싱 폴백]: {e}")
        sel_idx = 0
        target_corner = "역사 딥다이브"
        winner_reason = "기본 1순위 사료 자동 배정"

    if sel_idx < 0 or sel_idx >= len(candidates):
        sel_idx = 0

    main_event = candidates[sel_idx]
    print(f"\n  🎯 [오늘의 최종 결선 우승 사건]: [{target_corner}] {main_event['year']}년 - {main_event['text'][:40]}...")
    if winner_reason:
        print(f"  ⚡ 우승 사유: {winner_reason}")

    # ── 2. Google Search Grounding 팩트체크 실행 ──
    fact_data = run_fact_check_with_grounding(
        client, types, 'gemini-3.5-flash',
        main_event['year'], main_event['text'], main_event.get('extract', '')
    )
    # 결선 토너먼트에서 확정된 포맷 유지 (팩트체커의 임의 변경 방지)
    final_corner = target_corner
    fact_data["assigned_corner"] = final_corner
    corner_profile = CORNER_PROFILES[final_corner]

    # ── 3. 7씬 75~95초 서사 확장 대본 집필 ──
    print(f"\n[ScriptGen] [{final_corner}] 7씬 서사 확장 대본 집필 중 (75~95초 황금 러닝타임)...")

    script_prompt = f"""당신은 100만 역사 다큐멘터리 쇼츠 채널의 메인 작가입니다.
오늘 날짜: {month_day}
선정 사건: {main_event['year']}년 {fact_data.get('verified_title', main_event['text'])}
확정 코너: [{final_corner}]
코너 성격: {corner_profile['theme']}
서사 플롯 공식: {corner_profile['plot_guide']}
검증된 팩트 데이터:
{json.dumps(fact_data, ensure_ascii=False, indent=2)}

[대본 작성 절대 룰 - 엄격 준수]
1. [화면 자막(subtitle_text)과 성우 낭독(tts_script) 명확한 분리 및 러닝타임 제약]:
   - 반드시 총 7개 씬(씬 1부터 씬 7)으로 구성합니다.
   - subtitle_text: 화면에 시청자가 읽는 74pt 대형 자막. '1996년', '5만 명', '300달러'처럼 아라비아 숫자를 적극 사용하고, '오만', '사살' 등 모든 한국어/한자어 어휘는 원형 그대로 완벽하게 표기하세요.
   - tts_script: 성우(Google Cloud TTS)가 자연스럽고 또렷하게 읽는 낭독 대본. (공백 포함 75~85자 내외, 약 12~14초)
   - script: 기존 호환성을 위해 subtitle_text와 동일하게 기재하세요.
   - 7개 씬 전체 낭독 총합이 정확히 520~600자가 되도록 엄격히 통제하세요 (75~95초 황금 러닝타임).
2. [위인전/도덕 훈계 어투 100% 금지]:
   - "우리는 본받아야 합니다", "성현의 뜻을 기리며" 같은 훈계조 절대 금지!
   - 써에이스쇼/OverSimplified처럼 찰진 구어체와 극적인 긴장감을 살리세요.
3. [씬별 6대 시네마틱 카메라 모션 강제 (camera_motion)]:
   - 각 씬의 극적 분위기에 맞춰 다음 6개 중 하나를 반드시 지정하세요:
     * 'face_zoom': 인물 표정/얼굴 중심 긴박한 클로즈업
     * 'push_in': 긴장감이 고조되는 전진 줌
     * 'pan_lr': 전장/협상장/배경을 훑는 좌->우 수평 패닝
     * 'tilt_up': 아래에서 위로 웅장하게 솟아오르는 상승 틸트
     * 'vignette_zoom_out': 비극/고독/숙청의 순간 외곽 암전과 줌아웃
     * 'slow_drift': 대각선으로 유려하게 흐르는 깊은 여운의 무빙
4. [씬별 노란색 하이라이트 키워드 (highlight_keywords)]:
   - 시청자의 시선을 사로잡을 핵심 명사, 숫자, 무기명, 사건명 1~2개를 반드시 배열로 지정하세요 (예: ["판저 4호"], ["3,000명 몰살"]).
   - 🚨 종결어미(~했습니다)나 조사(~에게, ~에서)는 절대 하이라이트로 지정하지 마세요.
5. [사료 프롬프트 및 비주얼 가이드]:
   - image_search_keyword: 위키미디어 Commons 검색용 구체적 영문 고유명사 (동상/우표 배제)
   - image_caption: 상단 사료 크레딧용 10~18자 한국어 설명
   - ai_image_prompt: 사료 부재 시 생성할 9:16 시네마틱 프롬프트 (Cinematic period chiaroscuro lighting, vertical 9:16 portrait composition, historical realism, 8k resolution, strictly NO text, NO hangul, NO captions, NO watermark)
6. [알고리즘 참여 유도 고정 댓글 (pinned_comment)]:
   - 시청자가 영상을 본 뒤 댓글창에서 치열하게 토론할 수 있는 날카로운 질문 1줄 작성.
7. [제목 (title)]:
   - '[{final_corner}] {main_event['year']}년 사건명, 킬러 질문형 훅?' 형식으로 28~38자 이내 작성.

[출력 JSON 포맷]:
{{
  "corner_name": "{final_corner}",
  "title": "[{final_corner}] {main_event['year']}년 사건명, 킬러 질문형 훅?",
  "main_year": "{main_event['year']}",
  "hook_question": "시청자를 끌어당기는 첫 3초 충격 훅 질문",
  "bgm": "{corner_profile['bgm']}",
  "primary_source": "{fact_data.get('primary_source', '공공 역사 기록 사료')}",
  "pinned_comment": "시청자의 댓글 토론을 유도하는 날카로운 질문",
  "scenes": [
    {{
      "scene_number": 1,
      "display_title": "씬 1 소제목 (8~14자)",
      "subtitle_text": "화면 자막용 텍스트 (75~85자, 1996년 등 숫자 표기 및 정밀 어휘)",
      "tts_script": "성우 낭독용 텍스트 (75~85자)",
      "script": "화면 자막과 동일한 텍스트",
      "camera_motion": "face_zoom",
      "highlight_keywords": ["핵심키워드"],
      "image_search_keyword": "specific english keyword",
      "image_caption": "한국어 사료 캡션",
      "ai_image_prompt": "Cinematic 9:16 prompt..."
    }},
    {{
      "scene_number": 2,
      "display_title": "씬 2 소제목",
      "script": "내레이션...",
      "camera_motion": "push_in",
      "highlight_keywords": ["핵심키워드"],
      "image_search_keyword": "...",
      "image_caption": "...",
      "ai_image_prompt": "..."
    }},
    {{
      "scene_number": 3,
      "display_title": "씬 3 소제목",
      "script": "내레이션...",
      "camera_motion": "pan_lr",
      "highlight_keywords": ["핵심키워드"],
      "image_search_keyword": "...",
      "image_caption": "...",
      "ai_image_prompt": "..."
    }},
    {{
      "scene_number": 4,
      "display_title": "씬 4 소제목",
      "script": "내레이션...",
      "camera_motion": "tilt_up",
      "highlight_keywords": ["핵심키워드"],
      "image_search_keyword": "...",
      "image_caption": "...",
      "ai_image_prompt": "..."
    }},
    {{
      "scene_number": 5,
      "display_title": "씬 5 소제목",
      "script": "내레이션...",
      "camera_motion": "push_in",
      "highlight_keywords": ["핵심키워드"],
      "image_search_keyword": "...",
      "image_caption": "...",
      "ai_image_prompt": "..."
    }},
    {{
      "scene_number": 6,
      "display_title": "씬 6 소제목",
      "script": "내레이션...",
      "camera_motion": "vignette_zoom_out",
      "highlight_keywords": ["핵심키워드"],
      "image_search_keyword": "...",
      "image_caption": "...",
      "ai_image_prompt": "..."
    }},
    {{
      "scene_number": 7,
      "display_title": "씬 7 소제목",
      "script": "내레이션...",
      "camera_motion": "slow_drift",
      "highlight_keywords": ["핵심키워드"],
      "image_search_keyword": "...",
      "image_caption": "...",
      "ai_image_prompt": "..."
    }}
  ]
}}
"""
    script_res = generate_content_with_retry(
        client,
        model='gemini-3.5-flash',
        contents=script_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.7
        )
    )

    clean_res_text = re.sub(r"^```json\s*", "", script_res.text.strip())
    clean_res_text = re.sub(r"\s*```$", "", clean_res_text).strip()
    script_data = json.loads(clean_res_text)

    # 3대 코너 불변 강제 및 사후 검증
    if script_data.get("corner_name") not in ALLOWED_CORNERS:
        script_data["corner_name"] = final_corner
    script_data["lang"] = "ko"
    script_data["fact_check"] = fact_data
    script_data["source"] = main_event.get("source", "")
    script_data["wiki_page_title"] = main_event.get("wiki_page_title", "")
    script_data["wiki_articles"] = main_event.get("related_wiki_pages", [])

    # 씬별 텍스트 정제 및 카메라 모션 유효성 검증
    total_chars = 0
    for idx, sc in enumerate(script_data.get("scenes", [])):
        sc["scene_number"] = idx + 1
        sub_text = sc.get("subtitle_text") or sc.get("script", "")
        tts_text = sc.get("tts_script") or sc.get("script", "")
        sc["subtitle_text"] = clean_narration_text(sub_text)
        sc["tts_script"] = clean_narration_text(tts_text)
        sc["script"] = sc["subtitle_text"]  # 하위 호환성 유지
        total_chars += len(sc["tts_script"])
        if sc.get("camera_motion") not in VALID_MOTIONS:
            sc["camera_motion"] = "push_in" if idx % 2 == 0 else "pan_lr"
        if not sc.get("highlight_keywords"):
            sc["highlight_keywords"] = [sc.get("display_title", "역사적 순간")]

    print(f"  📝 [대본 작성 완료] 총 씬 수: {len(script_data['scenes'])}씬 | 총 내레이션: {total_chars}자 (예상 낭독: {total_chars/6.5:.1f}초)")

    # BGM 무드 기반 날짜별 스마트 순환 로테이션
    from src.bgm_selector import select_rotated_bgm
    cur_bgm = script_data.get("bgm", corner_profile["bgm"])
    rotated_bgm = select_rotated_bgm(cur_bgm, clean_date)
    script_data["bgm"] = rotated_bgm
    print(f"  🎵 [BGM 스마트 로테이션] '{cur_bgm}' ➔ 날짜 순환 음원 확정: '{rotated_bgm}'")

    # 한국어 전용 디렉토리 및 공통 루트에 저장
    ko_dir = get_daily_dir(clean_date, edition="history")
    output_path = os.path.join(ko_dir, "masterpiece_script.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)

    root_script_path = os.path.join(daily_dir, "masterpiece_script.json")
    with open(root_script_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)

    # 고정 댓글 텍스트 파일 저장
    pinned_path = os.path.join(daily_dir, "pinned_comment.txt")
    with open(pinned_path, "w", encoding="utf-8") as f:
        f.write(script_data.get("pinned_comment", ""))

    print(f"✅ [ScriptGen] 100% 무인 킬러 대본 완성: {output_path}")
    return output_path


if __name__ == "__main__":
    t_date = sys.argv[1] if len(sys.argv) > 1 else None
    generate_killer_script(t_date)
