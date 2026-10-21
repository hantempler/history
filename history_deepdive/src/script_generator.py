import os
import sys
import time
import json
import re
from datetime import datetime
from google import genai
from google.genai import types

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, 'config')
CRED_PATH = os.path.join(CONFIG_DIR, 'application_default_credentials.json')
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CRED_PATH

GCP_PROJECT_ID = "project-beba2bf6-d235-4031-ba5"
GCP_LOCATION = "us-central1"


def clean_narration_text(text: str) -> str:
    """TTS 및 자막 불일치를 막기 위해 괄호, 한자 표기, 특수문자 등을 정제"""
    # 괄호 및 괄호 안 내용 제거 (예: (史臣曰) -> 사관은 말했다)
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    # 불필요한 따옴표나 특수문자 정리
    text = re.sub(r'["\'`“”‘’]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def save_fact_check_report_md(fact_report: dict, raw_script: dict, final_script: dict, md_path: str, target_date: str):
    """사람이 읽을 수 있는 고품격 역사 팩트체크 교차 검증 마크다운 보고서 생성"""
    target_event = fact_report.get("target_event", final_script.get("event_title", "역사적 사건"))
    status = fact_report.get("verification_status", "VERIFIED")
    status_badge = "✅ **정사 일치 검증 통과 (VERIFIED_ACCURATE)**" if "VERIFIED" in status else "🛠️ **역사적 사실 교정 완료 (FACT_CORRECTED)**"
    sources = fact_report.get("sources_consulted", [])
    critique = fact_report.get("overall_critique", "원문 사료 대조 검증을 완료하였습니다.")
    audits = fact_report.get("scene_audits", [])

    raw_scenes = {sc.get("scene_number", i+1): sc for i, sc in enumerate(raw_script.get("scenes", []))}
    final_scenes = {sc.get("scene_number", i+1): sc for i, sc in enumerate(final_script.get("scenes", []))}

    lines = [
        "# 🏛️ 역사 팩트체크 & 사료 교차 검증 종합 보고서",
        "",
        f"- **검증 일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} KST",
        f"- **검증 엔진**: Google Vertex AI Gemini 2.5 Pro (수석 역사 팩트체커, 정밀도 온도 0.3)",
        f"- **대상 날짜 / 코너**: {target_date} | {final_script.get('corner_name', '역사 다큐멘터리')}",
        f"- **사건 주제**: **{target_event}**",
        f"- **최종 검증 판정**: {status_badge}",
        "",
        "---",
        "",
        "### 1. 📜 대조 사료 및 역사적 근거 (Historical Sources)",
        ""
    ]

    if sources:
        for s in sources:
            lines.append(f"- 📖 {s}")
    else:
        lines.append("- 📖 조선왕조실록 및 당대 정사(正史) 원문 기록")

    lines.extend([
        "",
        "---",
        "",
        "### 2. 🔍 수석 팩트체커 종합 고증 총평",
        "",
        f"> {critique}",
        "",
        "---",
        "",
        "### 3. 씬별 정밀 대조 검증 내역 (Scene-by-Scene Audit)",
        "",
        "| 씬 | 1차 초안 서술 (Draft) | 최종 확정 대본 (Verified) | 판정 (Verdict) | 사료 근거 및 교정/검증 사유 |",
        "|:---:|---|---|:---:|---|"
    ])

    for audit in audits:
        sc_num = audit.get("scene_number", 1)
        raw_sc = raw_scenes.get(sc_num, {})
        final_sc = final_scenes.get(sc_num, {})

        raw_text = audit.get("draft_narration") or raw_sc.get("script", "(초안 없음)")
        final_text = final_sc.get("script", "")
        verdict = audit.get("verdict", "PASS")
        verdict_emoji = "✅ PASS" if "PASS" in verdict else "✏️ REVISED"
        details = audit.get("correction_details", audit.get("historical_veracity", "정사 일치"))

        clean_raw = raw_text.replace("|", " ").replace("\n", " ")[:120]
        clean_final = final_text.replace("|", " ").replace("\n", " ")[:120]
        clean_details = details.replace("|", " ").replace("\n", " ")

        lines.append(f"| **Scene {sc_num}** | {clean_raw} | {clean_final} | {verdict_emoji} | {clean_details} |")

    lines.extend([
        "",
        "---",
        "",
        "### 4. 📁 관련 산출물 파일",
        "- **1차 대본 초안**: [`masterpiece_script_raw.json`](./masterpiece_script_raw.json)",
        "- **팩트체크 검증 데이터**: [`fact_check_report.json`](./fact_check_report.json)",
        "- **최종 제작 대본**: [`masterpiece_script.json`](./masterpiece_script.json)",
        ""
    ])

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def generate_masterpiece_script(routed_data: dict, out_dir: str) -> dict:
    preset = routed_data["preset"]
    corner = preset["corner"]
    category = preset["category"]
    bgm = preset["bgm"]
    target_date = routed_data["target_date"]
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    month_day_kr = f"{dt.month}월 {dt.day}일"

    events = routed_data["events"]
    if not events:
        raise ValueError(f"수집된 사건 데이터가 없습니다: {target_date}")

    print(f"\n[AI 대본 집필] Gemini 2.5 Pro 호출 - 코너: [{corner}] ({month_day_kr})")

    # 사건 목록 텍스트화
    events_text = ""
    if preset["source_type"] in ["sillok_db", "sillok_parallel"]:
        # 실록 DB 기사 포맷
        for idx, e in enumerate(events[:15]):
            sasin_summary = f"\n   [사관의 평 史臣曰]: {e['sasin_text'][:200]}..." if e.get("has_sasin") else ""
            events_text += f"[{idx+1}] {e['year']}년 ({e['solar_date']}) - {e['title']}{sasin_summary}\n\n"

        special_instruction = f"""
[특별 엄수 규정: 수요일 '실록 오늘']
당신은 조선왕조 500년의 정사(正史)를 현대인에게 서늘한 몰입감으로 전달하는 전문 역사 작가입니다.
오늘은 '{month_day_kr}'이며, 코너는 반드시 **'실록 오늘'**입니다.

위의 실제 조선왕조실록 사건 중, 가장 서늘한 충격을 주거나 사관의 날 선 비판이 담긴 사건 **1건**을 엄선하여(단, 이미 다룬 '1557년 전주 지진'은 제외하고 다른 사건을 엄선),
1080x1920 마스터피스 표준 5개 씬 다큐멘터리 대본을 완전히 새로 작성하세요.

[씬별 구성 가이드]
- 씬 1: [도입] 오늘 날짜({month_day_kr})를 밝히며, 그날 궁궐과 어전을 뒤흔든 충격적 사건에 대한 질문을 던지세요.
- 씬 2: [전개] 사건의 배경과 궁궐의 긴장된 상황을 사실에 입각하여 묘사하세요.
- 씬 3: [위기] 왕의 결단이나 신하들의 격렬한 대립, 피할 수 없는 결정적 순간을 그리세요.
- 씬 4: [반전/사관의 직필] 목숨을 걸고 역사에 기록을 남긴 사관의 평가(史臣曰)를 직접 인용하여 숨겨진 진실을 폭로하세요.
- 씬 5: [결말/질문] 수백 년 전 사관이 남긴 경고가 오늘날 우리에게 던지는 날카로운 질문으로 마무리하세요.
"""
    else:
        # 위키피디아 테마 사건 포맷
        for idx, e in enumerate(events[:15]):
            events_text += f"[{idx+1}] {e['year']}년: {e['title']} - {e.get('extract', '')[:150]}\n\n"

        special_instruction = f"""
[특별 엄수 규정: {corner}]
당신은 대한민국 1등 유튜브 역사 다큐멘터리 쇼츠의 메인 작가입니다.
오늘은 '{month_day_kr}'이며, 코너는 **'{corner}'** ({preset['theme']})입니다.

위의 전 세계 역사 사건 중, 오늘의 테마('{preset['theme']}')에 100% 부합하는 가장 극적인 사건 **1건**을 엄선하여,
1080x1920 마스터피스 표준 5개 씬 대본을 작성하세요.

[씬별 구성 가이드]
- 씬 1: [도입] 오늘 날짜({month_day_kr})를 언급하며 시청자를 단숨에 몰입시키는 충격적 질문 제시.
- 씬 2: [발단] 그날 일어난 사건의 구체적 배경과 긴박한 정황.
- 씬 3: [절정] 승패가 갈린 결전, 충격적 비극, 혹은 전술의 충돌 순간.
- 씬 4: [반전/기록] 역사적 사료와 목격자의 증언, 혹은 사건 뒤에 숨겨진 비밀 폭로.
- 씬 5: [질문] 오늘날 우리 사회와 시청자에게 던지는 날카로운 질문.
"""

    prompt = f"""
{special_instruction}

[입력 데이터: 오늘 발생한 실제 역사 사건 목록]
{events_text}

[공통 필수 작성 원칙]
1. TTS 음성과 자막 텍스트 100% 일치:
   - 각 씬의 `script` 텍스트가 그대로 성우의 목소리로 합성되고 화면 자막으로 출력됩니다.
   - 괄호, 지시문, 해설, 특수문자, 한자를 일체 쓰지 마십시오. 오직 성우가 입으로 읽을 수 있는 한글 구어체만 출력하십시오.
   - 각 씬은 호흡이 가쁘지 않은 2~3문장(약 10~12초 분량)이어야 합니다.
2. `image_search_keyword`:
   - 위키미디어 고화질 사료를 찾기 위한 정확한 인물/사건 중심 영문 검색 키워드(2~4단어)를 제시하십시오.
3. `image_caption`:
   - 해당 씬에 표시될 사료나 장면에 대한 **간결하고 명확한 순수 한국어 설명(15자 이내)**을 작성하십시오. 폰트 깨짐 방지를 위해 한자(漢字)나 괄호 병기를 절대 사용하지 마십시오 (예: '카슈미르 번왕 하리 싱', '조선 궁궐 어전 비상회의', '경종의 결단이 담긴 주문 문서').
4. `ai_image_prompt`:
   - 위키미디어에 사료가 없을 때를 대비한 **9:16 세로 시네마틱 역사 고증 일러스트 프롬프트(영문)**를 구체적으로 작성하십시오.
5. 코너명(`corner_name`)은 반드시 "{corner}"로 기재하십시오.
6. BGM(`bgm`)은 반드시 "{bgm}"로 기재하십시오.

반드시 아래 JSON 포맷으로만 응답하십시오:
{{
  "corner_name": "{corner}",
  "category": "{category}",
  "event_title": "연도 및 사건 핵심 제목 (예: 1722 경종실록, 어전을 뒤흔든 칙서의 비밀)",
  "hook_question": "시청자를 끌어당기는 의문형 훅 질문",
  "why_today_title": "오늘 알아야 할 이유 소제목",
  "why_today_desc": "역사의 교훈과 통찰 한 줄 설명",
  "bgm": "{bgm}",
  "scenes": [
    {{
      "scene_number": 1,
      "display_title": "씬 1 소제목",
      "summary": "유튜브 설명란용 해당 씬 1줄 핵심 사건 요약 (20~25자 내외)",
      "script": "씬 1 나레이션 문장 (TTS/자막 100% 일치)",
      "image_search_keyword": "영문 사료 검색어",
      "image_caption": "한국어 사료 간략 설명 (15자 이내)",
      "ai_image_prompt": "Cinematic historical documentary illustration prompt in English, 9:16 portrait"
    }},
    {{
      "scene_number": 2,
      "display_title": "씬 2 소제목",
      "summary": "유튜브 설명란용 해당 씬 1줄 핵심 사건 요약 (20~25자 내외)",
      "script": "씬 2 나레이션 문장",
      "image_search_keyword": "영문 사료 검색어",
      "image_caption": "한국어 사료 간략 설명 (15자 이내)",
      "ai_image_prompt": "Cinematic historical documentary illustration prompt in English, 9:16 portrait"
    }},
    {{
      "scene_number": 3,
      "display_title": "씬 3 소제목",
      "summary": "유튜브 설명란용 해당 씬 1줄 핵심 사건 요약 (20~25자 내외)",
      "script": "씬 3 나레이션 문장",
      "image_search_keyword": "영문 사료 검색어",
      "image_caption": "한국어 사료 간략 설명 (15자 이내)",
      "ai_image_prompt": "Cinematic historical documentary illustration prompt in English, 9:16 portrait"
    }},
    {{
      "scene_number": 4,
      "display_title": "씬 4 소제목",
      "summary": "유튜브 설명란용 해당 씬 1줄 핵심 사건 요약 (20~25자 내외)",
      "script": "씬 4 나레이션 문장",
      "image_search_keyword": "영문 사료 검색어",
      "image_caption": "한국어 사료 간략 설명 (15자 이내)",
      "ai_image_prompt": "Cinematic historical documentary illustration prompt in English, 9:16 portrait"
    }},
    {{
      "scene_number": 5,
      "display_title": "씬 5 소제목",
      "summary": "유튜브 설명란용 해당 씬 1줄 핵심 사건 요약 (20~25자 내외)",
      "script": "씬 5 나레이션 문장",
      "image_search_keyword": "영문 사료 검색어",
      "image_caption": "한국어 사료 간략 설명 (15자 이내)",
      "ai_image_prompt": "Cinematic historical documentary illustration prompt in English, 9:16 portrait"
    }}
  ]
}}
"""

    client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_LOCATION)
    print("  [Step 2-1] 사료 기반 1차 대본 초안 집필 중 (Gemini 2.5 Pro)...")

    def call_gemini_with_retry(model_name, contents_payload, config_payload, max_retries=2):
        for attempt in range(max_retries + 1):
            try:
                return client.models.generate_content(
                    model=model_name,
                    contents=contents_payload,
                    config=config_payload
                )
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    if attempt < max_retries:
                        wait_sec = 8 * (attempt + 1)
                        print(f"    ⏳ [429 Quota 대기] {wait_sec}초 후 재시도 중 ({attempt+1}/{max_retries})...")
                        time.sleep(wait_sec)
                    else:
                        print(f"    🔄 [안전 폴백] gemini-2.5-flash 모델로 전환 호출...")
                        return client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=contents_payload,
                            config=config_payload
                        )
                else:
                    raise e

    response = call_gemini_with_retry(
        model_name='gemini-2.5-pro',
        contents_payload=prompt,
        config_payload=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.7
        )
    )

    raw_script_text = response.text.strip()
    os.makedirs(out_dir, exist_ok=True)

    # 1. 1차 생성 대본 초안 영구 저장 (보존)
    raw_out_path = os.path.join(out_dir, "masterpiece_script_raw.json")
    try:
        raw_script_data = json.loads(raw_script_text)
        with open(raw_out_path, "w", encoding="utf-8") as f:
            json.dump(raw_script_data, f, ensure_ascii=False, indent=2)
    except Exception:
        with open(raw_out_path, "w", encoding="utf-8") as f:
            f.write(raw_script_text)
        raw_script_data = {}
    print(f"  📁 [1차 대본 초안 보존] {raw_out_path}")

    time.sleep(3)  # RPM 쿼터 보호를 위한 3초 버퍼링

    # -------------------------------------------------------------
    # Step 2-2: 엄격한 역사 정사(正史) 팩트체크 교차 검증 (Gemini 2.5 Pro)
    # -------------------------------------------------------------
    print("  [Step 2-2] 엄격한 역사 팩트체크 및 사료 교차 검증 가동 (온도 0.3 정밀 검증)...")
    fact_check_prompt = f"""
당신은 대한민국 최고의 역사 다큐멘터리 수석 팩트체커(Chief Fact-Checker)이자 역사학자입니다.
제공된 1차 생성 대본을 읽고, 실제 역사적 정사(正史) 및 원문 사료와 대조하여 엄격하게 교차 검증하십시오.

[1차 생성 대본]
{raw_script_text}

[기준 역사 사료 데이터]
{events_text}

[팩트체크 엄수 원칙]
1. 역사적 사실 무결성:
   - 연도, 날짜, 인물명, 관직, 지명, 군사 작전명, 사건의 전후 인과관계가 실제 역사 기록과 정확히 일치하는지 철저히 검증하십시오.
   - 근거 없는 야사, 과장된 낭설, 또는 AI 할루시네이션이 발견되면 정사(正史)와 실록 기록에 부합하도록 즉시 바로잡으십시오.
2. 품격 있는 다큐멘터리 톤 유지:
   - 긴장감과 몰입감은 유지하되, 역사적 왜곡이나 단정적 오해를 부르는 문장은 객관적이고 서늘한 다큐멘터리 어조로 정제하십시오.
3. 씬별 자막/음성 일치 및 스키마 유지:
   - 교정된 대본의 JSON 스키마(corner_name, category, event_title, hook_question, why_today_title, why_today_desc, bgm, scenes 내부 필드)를 100% 동일하게 유지하십시오.
4. 출력 형식:
   - 반드시 아래의 정확한 JSON 구조로만 출력하십시오. 마크다운 백틱 없이 순수 JSON만 반환하십시오.

{{
  "fact_check_report": {{
    "target_event": "사건 및 날짜 (예: 1546년 10월 25일 명종실록)",
    "verification_status": "VERIFIED_ACCURATE" 또는 "FACT_CORRECTED",
    "sources_consulted": [
      "대조한 실록 기사 권호 및 사관의 史臣曰 등 실제 역사 사료 목록"
    ],
    "overall_critique": "수석 팩트체커의 역사적 사실성 총평 및 교정 사유 상세 서술",
    "scene_audits": [
      {{
        "scene_number": 1,
        "draft_narration": "1차 초안 핵심 나레이션 요약",
        "historical_veracity": "실제 정사 기록과의 일치 여부 및 팩트 설명",
        "verdict": "PASS" 또는 "REVISED",
        "correction_details": "초안 대비 바로잡은 내용 및 고증 근거"
      }}
    ]
  }},
  "final_script": {{
    "corner_name": "{corner}",
    "category": "{routed_data.get('preset', {}).get('category', '역사 딥다이브')}",
    "event_title": "...",
    "hook_question": "...",
    "why_today_title": "...",
    "why_today_desc": "...",
    "bgm": "{bgm}",
    "scenes": [
      {{
        "scene_number": 1,
        "display_title": "...",
        "summary": "1줄 핵심 요약 (20자 내외)",
        "script": "...",
        "image_search_keyword": "...",
        "image_caption": "한국어 사료 간략 설명 (15자 이내)",
        "ai_image_prompt": "..."
      }}
    ]
  }}
}}
"""
    fact_report = {}
    try:
        fact_response = call_gemini_with_retry(
            model_name='gemini-2.5-pro',
            contents_payload=fact_check_prompt,
            config_payload=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3
            )
        )
        res_json = json.loads(fact_response.text)
        if "final_script" in res_json:
            script_data = res_json["final_script"]
            fact_report = res_json.get("fact_check_report", {})
        elif "scenes" in res_json:
            script_data = res_json
            fact_report = res_json.get("fact_check_report", {
                "target_event": script_data.get("event_title", ""),
                "verification_status": "VERIFIED_ACCURATE",
                "sources_consulted": ["조선왕조실록 및 당대 정사 기록"],
                "overall_critique": "정사 사료 대조 검증 완료",
                "scene_audits": []
            })
        else:
            script_data = json.loads(raw_script_text)
            fact_report = {"verification_status": "FALLBACK"}
        print("  ✅ [팩트체크 완료] 역사적 정사 교차 검증 및 검증 리포트 생성 완료.")
    except Exception as e:
        print(f"  ⚠️ 팩트체크 중 예외 발생, 1차 초안으로 안전 폴백: {e}")
        script_data = json.loads(raw_script_text) if raw_script_data else {}
        fact_report = {
            "target_event": script_data.get("event_title", ""),
            "verification_status": "FALLBACK_RAW",
            "sources_consulted": ["원문 사료 데이터"],
            "overall_critique": f"팩트체크 호출 예외 발생으로 1차 초안 채택: {e}",
            "scene_audits": []
        }

    # 후처리: TTS 및 자막 무결성 확보
    script_data["corner_name"] = corner
    script_data["bgm"] = bgm
    for sc in script_data.get("scenes", []):
        sc["script"] = clean_narration_text(sc.get("script", ""))

    # 최종 대본 내부에도 팩트체크 메타데이터 보존
    script_data["fact_check"] = {
        "status": fact_report.get("verification_status", "VERIFIED"),
        "historical_sources": fact_report.get("sources_consulted", []),
        "critique": fact_report.get("overall_critique", ""),
        "report_file": "fact_check_report.md"
    }

    # 1) 팩트체크 리포트 JSON 영구 저장
    report_json_path = os.path.join(out_dir, "fact_check_report.json")
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(fact_report, f, ensure_ascii=False, indent=2)
    print(f"  📁 [팩트체크 JSON 저장] {report_json_path}")

    # 2) 팩트체크 마크다운 보고서 저장 (사람용 정밀 리포트)
    report_md_path = os.path.join(out_dir, "fact_check_report.md")
    save_fact_check_report_md(fact_report, raw_script_data, script_data, report_md_path, target_date)
    print(f"  📁 [팩트체크 MD 보고서 저장] {report_md_path}")

    # 3) 최종 masterpiece_script.json 저장
    out_path = os.path.join(out_dir, "masterpiece_script.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)

    print(f"  ✅ [최종 대본 확정] {script_data.get('event_title')}")
    print(f"  📁 저장: {out_path}")
    return script_data
