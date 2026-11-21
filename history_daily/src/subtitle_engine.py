"""스타이즈본 벤치마킹 다이내믹 자막 엔진 (subtitle_engine.py).
유튜브 지식 쇼츠(1분만, 사물궁이, 지식인사이드) 자막 공식 완벽 이식:
1. Gemini 2.5 Flash 기반 자연스러운 발화 호흡 구문 분할 (Dynamic Chunking, 12~22자)
2. 시선 강탈 역사 핵심 키워드 비비드 옐로우/골드(&H0000E6FF& / #FFD700) 하이라이트
3. FFmpeg silencedetect 기반 음성 시작(lead-in) 감지 및 문장부호 호흡 가중치(쉼표 +3.5, 마침표 +4.5) 배분
4. 모바일 UI 완벽 회피 세이프존(MarginV=480 / y=1390) 배치
5. ASS 네이티브 번인 및 워드 레벨 하이라이트 글래스 플레이트(PNG) 듀얼 지원
"""
import os
import sys
import re
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

SRC_DIR = Path(__file__).resolve().parent
BASE_DIR = SRC_DIR.parent
CONFIG_DIR = BASE_DIR / "config"

# GCP 설정 로드
try:
    from .config import GCP_PROJECT_ID, GCP_LOCATION, FONT_MAIN
except ImportError:
    from src.config import GCP_PROJECT_ID, GCP_LOCATION, FONT_MAIN


# ---------------------------------------------------------------------------
# 0. 한글 발음 표기 -> 아라비아 숫자/날짜 표기 100% 보존 변환 (Starisborn 엔진 이식)
# ---------------------------------------------------------------------------
STOP_ENDINGS = (
    "습니다", "었습니다", "았습니다", "였습니다", "있었습니다", "없었습니다",
    "뿐이었습니다", "뿐이었다", "돌았지만", "했지만", "였지만", "이라며", "라며",
    "에게", "에서", "으로", "까지", "부터", "하고", "되고", "하며", "합니다",
    "입니다", "립니다", "칩니다", "옵니다", "냅니다", "봅니다", "줍니다", "겪습니다",
    "됩니다", "했습니다", "당했습니다", "받았습니다", "밝혀집니다", "드러납니다", "시작됩니다",
    "끝납니다", "벌어집니다", "넘어갑니다", "이어집니다", "남겼습니다", "나섭니다"
)


def is_stop_word(word: str) -> bool:
    """서술어, 종결어미, 조사 등 하이라이트 배제 대상 판별."""
    clean = re.sub(r'[,.!?\'"“”~]', '', word).strip()
    if len(clean) < 2:
        return True
    if any(clean.endswith(se) for se in STOP_ENDINGS):
        return True
    # 한국어 서술어 종결어미 정규식 (습니다, ㅂ니다, 합니다, 됩니다, 였다, 했다 등)
    if re.search(r'(습니다|ㅂ니다|합니다|됩니다|입니다|였다|했다|됐다|었다|았다|있었다|없었다|이었죠|였죠|했죠|됐죠|있었죠|없었죠|일까요|을까요|했나요|인가요)$', clean):
        return True
    return False


def format_sub_display(text: str) -> str:
    """내레이션 전문의 한글 발음 표기를 화면 자막용 아라비아 숫자/날짜/단위 표기로 100% 정규화 변환."""
    if not text:
        return ""

    t = text

    sino_map = {
        '영': 0, '공': 0, '일': 1, '이': 2, '삼': 3, '사': 4,
        '오': 5, '육': 6, '칠': 7, '팔': 8, '구': 9
    }

    def parse_sino(s):
        val = 0
        cur = 0
        for ch in s:
            if ch in sino_map:
                cur = sino_map[ch]
            elif ch == '십':
                val += (cur if cur != 0 else 1) * 10
                cur = 0
            elif ch == '백':
                val += (cur if cur != 0 else 1) * 100
                cur = 0
            elif ch == '천':
                val += (cur if cur != 0 else 1) * 1000
                cur = 0
        return val + cur

    native_tens = {'스물': 20, '서른': 30, '마흔': 40, '쉰': 50, '예순': 60, '일흔': 70, '여든': 80, '아흔': 90}
    native_ones = {'하나': 1, '한': 1, '둘': 2, '두': 2, '셋': 3, '세': 3, '넷': 4, '네': 4, '다섯': 5, '여섯': 6, '일곱': 7, '여덟': 8, '아홉': 9, '열': 10}

    def parse_native(s):
        val = 0
        rem = s
        if rem.startswith('열') and len(rem) > 1:
            val += 10
            rem = rem[1:]
        else:
            for k, v in native_tens.items():
                if rem.startswith(k):
                    val += v
                    rem = rem[len(k):]
                    break
        for k, v in native_ones.items():
            if rem == k:
                val += v
                rem = ''
                break
        if rem == '' and val > 0:
            return val
        return None

    def repl_digit_year(m):
        digits = "".join(str(sino_map[ch]) for ch in m.group(1))
        val = int(digits)
        if 1000 <= val <= 2099:
            return f"{val}년"
        return m.group(0)

    def repl_year(m):
        full = m.group(1)
        try:
            val = parse_sino(full)
            if 1000 <= val <= 2099:
                return f"{val}년"
        except Exception:
            pass
        return m.group(0)

    # 1-1. 연도: 4자리 연속 숫자음 (일구구육년 -> 1996년, 일구팔삼년 -> 1983년)
    t = re.sub(r'(?<![가-힣])([영공일이삼사오육칠팔구]{4})년', repl_digit_year, t)

    # 1-2. 연도: 자릿수 결합 (천구백구십육년 -> 1996년, 이천이십육년 -> 2026년)
    t = re.sub(r'((?:천[팔구]백|이천)[영공일이삼사오육칠팔구십백천]*)년', repl_year, t)

    # 2. 월: 시월, 유월, 십월 등
    month_map = {
        '일월': '1월', '이월': '2월', '삼월': '3월', '사월': '4월',
        '오월': '5월', '유월': '6월', '칠월': '7월', '팔월': '8월',
        '구월': '9월', '시월': '10월', '십월': '10월',
        '십일월': '11월', '십이월': '12월'
    }
    for k, v in month_map.items():
        t = re.sub(rf'(?<![가-힣]){k}', v, t)

    # 3. 일: 1일 ~ 31일 (날짜 맥락 한정: 조사, 공백, 문장부호 또는 문자열 끝)
    def repl_day(m):
        full = m.group(1)
        try:
            val = parse_sino(full)
            if 1 <= val <= 31:
                return f"{val}일"
        except Exception:
            pass
        return m.group(0)

    t = re.sub(r'(?<![가-힣])([일이삼사오육칠팔구십]+)일(?=[\s,.\'\"~-]|$|부터|까지|에|은|는|이|가|도|로|만|간)', repl_day, t)

    # 4. 일반 수사 + 단위 결합 (달러, 원, 명, 개, 분, 초, 시간, %, 퍼센트, 척, 등, 위, 배, 대)
    unit_pattern = r'(?<![가-힣])([일이삼사오육칠팔구십백천]+)\s*(달러|원|엔|위안|파운드|분|초|시간|퍼센트|%|프로|도|살|세|명|개|장|권|척|곡|편|회|등|위|점|배|대|병|잔|골|승|패)'
    def repl_unit(m):
        full = m.group(1)
        unit = m.group(2)
        try:
            val = parse_sino(full)
            if val > 0:
                if unit in ['퍼센트', '프로']:
                    return f"{val}%"
                return f"{val}{unit}"
        except Exception:
            pass
        return m.group(0)

    t = re.sub(unit_pattern, repl_unit, t)

    # 5. 고유어 수사 + 단위 (스물다섯 살, 세 명, 두 개 등)
    def repl_native_unit(m):
        word = m.group(0).strip()
        unit = m.group(2)
        num_part = word[:-len(unit)].strip()
        val = parse_native(num_part)
        if val is not None:
            return f"{val}{unit}"
        return m.group(0)

    t = re.sub(r'(?<![가-힣])([스서마쉰예일여아열한두세네다여일여아][가-힣]*?)\s*(살|세|명|개|장|권|척|곡|편|회|대|병|잔|골|점)', repl_native_unit, t)

    # 6. 큰 수 단위 (오만 명 -> 5만 명, 백만 -> 100만, 오백 달러 -> 500달러)
    def repl_man(m):
        num_str = m.group(1)
        val = parse_sino(num_str)
        unit_trail = m.group(2) or ''
        if val > 0:
            return f"{val}만{unit_trail}"
        return m.group(0)

    t = re.sub(r'(?<![가-힣])([일이삼사오육칠팔구십]+)만(\s*명|\s*원|\s*달러|\s*장|\s*개|\s*뷰|\s*원)?', repl_man, t)
    t = re.sub(r'(?<![가-힣])백만(\s*명|\s*원|\s*달러|\s*장|\s*개|\s*뷰)?', r'100만\1', t)
    t = re.sub(r'(?<![가-힣])천만(\s*명|\s*원|\s*달러|\s*장|\s*개|\s*뷰)?', r'1,000만\1', t)
    t = re.sub(r'(?<![가-힣])일억(\s*명|\s*원|\s*달러|\s*장|\s*개)?', r'1억\1', t)
    t = re.sub(r'(?<![가-힣])십억(\s*명|\s*원|\s*달러|\s*장|\s*개)?', r'10억\1', t)
    t = re.sub(r'(?<![가-힣])백억(\s*명|\s*원|\s*달러|\s*장|\s*개)?', r'100억\1', t)
    t = re.sub(r'(?<![가-힣])천억(\s*명|\s*원|\s*달러|\s*장|\s*개)?', r'1,000억\1', t)
    t = re.sub(r'(?<![가-힣])일조(\s*원|\s*달러)?', r'1조\1', t)

    return t


# ---------------------------------------------------------------------------
# 1. FFmpeg 음성 시작 무음(Lead-in) 정밀 감지
# ---------------------------------------------------------------------------
def get_audio_voice_activity(audio_path, ffmpeg_bin="ffmpeg", min_silence_dur=0.18, silence_thresh_db=-28):
    """FFmpeg silencedetect로 실제 음성 시작(lead_in) 구간을 정밀 측정하여 첫 자막 싱크 일치."""
    if not os.path.exists(audio_path):
        return 0.0

    cmd = [
        ffmpeg_bin, "-i", str(audio_path),
        "-af", f"silencedetect=noise={silence_thresh_db}dB:d={min_silence_dur}",
        "-f", "null", "-"
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        lead_in = 0.0
        for line in r.stderr.splitlines():
            if "silence_start: 0" in line or "silence_start: 0.0" in line:
                continue
            if "silence_end:" in line:
                m = re.search(r"silence_end:\s*([0-9.]+)", line)
                if m and lead_in == 0.0:
                    lead_in = min(0.35, float(m.group(1)))
                    break
        return lead_in
    except Exception as e:
        return 0.0


# ---------------------------------------------------------------------------
# 2. 규칙 기반 호흡 단위 청킹 (Fallback)
# ---------------------------------------------------------------------------
def rule_based_chunking(text, lang="ko"):
    """한국어/영어 구문 및 문장부호 기준 자연스러운 호흡 단위 분할 알고리즘."""
    if lang == "en":
        words = text.strip().split()
        chunks = []
        cur_words = []
        for w in words:
            cur_words.append(w)
            if len(cur_words) >= 5 or w.endswith((".", ",", "!", "?", ";", ":")):
                chunks.append(" ".join(cur_words))
                cur_words = []
        if cur_words:
            chunks.append(" ".join(cur_words))

        results = []
        for c in chunks:
            clean_words = [w.strip(".,?!'\"[]():;") for w in c.split() if len(w.strip(".,?!'\"[]():;")) >= 4]
            longest = max(clean_words, key=len) if clean_words else ""
            results.append({
                "text": c.strip(),
                "highlight": longest
            })
        return results

    # 한국어 기본 청킹
    raw_parts = re.split(r'([,?!.]\s*)', text)
    tokens = []
    for i in range(0, len(raw_parts), 2):
        chunk = raw_parts[i]
        if i + 1 < len(raw_parts):
            chunk += raw_parts[i + 1]
        chunk = chunk.strip()
        if chunk:
            tokens.append(chunk)

    chunks = []
    for tok in tokens:
        if len(tok) <= 22:
            chunks.append(tok)
        else:
            words = tok.split(" ")
            mid = max(1, len(words) // 2)
            chunks.append(" ".join(words[:mid]))
            chunks.append(" ".join(words[mid:]))

    results = []
    for c in chunks:
        words = [w.strip(".,?!'\"[]()") for w in c.split(" ") if len(w.strip(".,?!'\"[]()")) >= 2]
        longest = max(words, key=len) if words else ""
        results.append({
            "text": c.strip(),
            "highlight": longest
        })
    return results


# ---------------------------------------------------------------------------
# 3. Gemini 2.5 Flash 기반 지능형 다이내믹 청킹 & 키워드 하이라이트
# ---------------------------------------------------------------------------
def analyze_dynamic_chunks(scenes, lang="ko", gcp_project_id=GCP_PROJECT_ID, gcp_location=GCP_LOCATION):
    """Gemini 2.5 Flash를 이용해 역사 쇼츠 최적화 호흡 단위 청크 및 킬러 키워드 하이라이트 추출."""
    has_existing = all(bool(sc.get("chunks")) and isinstance(sc.get("chunks"), list) and len(sc.get("chunks")) > 0 for sc in scenes)
    if has_existing:
        print(f"  ✨ [Subtitle] 이미 대본에 분할된 자막 청크가 존재하여 즉시 재사용합니다 ({len(scenes)}씬).")
        return [{"scene_number": sc.get("scene_number", sc.get("scene_no", idx+1)), "chunks": sc["chunks"]} for idx, sc in enumerate(scenes)]

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(vertexai=True, project=gcp_project_id, location=gcp_location)

        scenes_input = []
        for sc in scenes:
            s_num = sc.get("scene_number", sc.get("scene_no", 1))
            scenes_input.append({
                "scene_number": s_num,
                "caption": sc.get("image_caption") or sc.get("display_title", ""),
                "script": sc.get("script", "")
            })

        if lang == "en":
            system_instruction = (
                "You are the senior subtitle director for a 1M subscriber global history documentary YouTube channel.\n"
                "Split each scene's English narration into natural speech breathing chunks of 4 to 7 words (about 20-35 characters).\n"
                "Do NOT split into tiny 1-2 word fragments; maintain clear, easy-to-read single-line context.\n"
                "In each chunk, select exactly 1 gripping key historical keyword or phrase (event, person, year, decisive action) for the highlight field.\n"
                "Do NOT alter or omit any original words."
            )
            prompt = f"""
Split the following English history documentary narrations into natural speech subtitle chunks.

[Input Scenes]
{json.dumps(scenes_input, ensure_ascii=False, indent=2)}

[Output JSON Format - JSON ONLY]
{{
  "scenes": [
    {{
      "scene_number": 1,
      "chunks": [
        {{
          "text": "In the cold October of 1917,",
          "highlight": "October of 1917"
        }},
        {{
          "text": "the Russian Empire stood on the brink of collapse.",
          "highlight": "Russian Empire"
        }}
      ]
    }}
  ]
}}
"""
        else:
            system_instruction = (
                "당신은 구독자 100만 유튜브 역사 지식 쇼츠의 수석 자막 디렉터입니다.\n"
                "각 씬의 내레이션을 성우의 자연스러운 발화 호흡에 맞추어 2.0~3.5초(약 12~22자 내외)의 '의미 있는 구문 덩어리'로 분할하세요.\n"
                "절대 3~4글자 단위로 자잘하게 쪼개지 말고, 시청자가 한눈에 읽기 편안한 한 줄 문맥 단위여야 합니다.\n"
                "각 청크마다 시청자의 시선을 순간적으로 사로잡을 수 있는 '핵심 키워드'(역사적 사건/인물/연도/결정적 행동) 1개를 highlight 필드에 지정하세요.\n"
                "텍스트의 원본 글자나 의미를 절대 누락하거나 임의로 변형하지 마세요."
            )
            prompt = f"""
아래 역사 씬 목록의 내레이션을 유튜브 쇼츠용 자연스러운 호흡 자막 청크로 분할해주세요.

[입력 씬 목록]
{json.dumps(scenes_input, ensure_ascii=False, indent=2)}

[출력 형식 - 반드시 JSON만 출력]
{{
  "scenes": [
    {{
      "scene_number": 1,
      "chunks": [
        {{
          "text": "로마 공화정의 영웅 율리우스 카이사르,",
          "highlight": "율리우스 카이사르"
        }},
        {{
          "text": "종신 독재관이 되며 공화정을 위협했습니다.",
          "highlight": "종신 독재관"
        }}
      ]
    }}
  ]
}}
"""
        resp = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                temperature=0.2
            )
        )
        data = json.loads(resp.text.strip())
        analyzed_scenes = data.get("scenes", [])
        # 100% 키워드 하이라이트 보장 및 정합성 검증
        for sc in analyzed_scenes:
            for c in sc.get("chunks", []):
                txt = c.get("text", "").strip()
                hl = c.get("highlight", "").strip()
                if not hl or hl.lower() not in txt.lower():
                    words = [w.strip(".,?!'\"[]()~") for w in txt.split() if len(w.strip(".,?!'\"[]()~")) >= 2]
                    c["highlight"] = max(words, key=len) if words else ""
        print(f"  ✨ [Subtitle] Gemini 2.5 Flash 기반 다이내믹 자막 청크 & 키워드 분할 완료 ({len(analyzed_scenes)}씬)")
        return analyzed_scenes
    except Exception as e:
        print(f"  ⚠️ [Subtitle] Gemini AI 분할 실패, 규칙 기반(Rule-based) 호흡 분할 적용: {e}")
        fallback_scenes = []
        for sc in scenes:
            s_num = sc.get("scene_number", sc.get("scene_no", 1))
            fallback_scenes.append({
                "scene_number": s_num,
                "chunks": rule_based_chunking(sc.get("script", ""), lang=lang)
            })
        return fallback_scenes


# ---------------------------------------------------------------------------
# 4. 문장부호 호흡 가중치 기반 정밀 타이밍 산출
# ---------------------------------------------------------------------------
def calculate_weighted_timings(chunks, total_duration, lead_in=0.0):
    """
    문장 부호(쉼표 +3.5, 마침표 +4.5)에 호흡 가중치를 주어 실제 성우의 발화 및 멈춤 호흡과 자막을 100% 동기화.
    반환: [(chunk_dict, start_sec, end_sec), ...]
    """
    if not chunks:
        return []

    weights = []
    for c in chunks:
        txt = c["text"].strip()
        w = max(1.0, len(re.sub(r'\s+', '', txt)))
        if txt.endswith((',', '!', '?')):
            w += 3.5  # 쉼표/느낌표 호흡 휴지 가중치
        elif txt.endswith('.'):
            w += 4.5  # 마침표 정적 휴지 가중치
        weights.append(w)

    total_weight = sum(weights) if sum(weights) > 0 else 1.0
    available_dur = max(0.8, total_duration - lead_in)

    timings = []
    t_cursor = lead_in
    for i, (c, w) in enumerate(zip(chunks, weights)):
        c_dur = available_dur * (w / total_weight)
        c_end = t_cursor + c_dur
        if i == len(chunks) - 1:
            c_end = total_duration

        timings.append((c, round(t_cursor, 3), round(c_end, 3)))
        t_cursor = c_end

    return timings


# ---------------------------------------------------------------------------
def get_sub_font(size, font_path=FONT_MAIN):
    import io
    try:
        with open(font_path, "rb") as f:
            return ImageFont.truetype(io.BytesIO(f.read()), size)
    except Exception:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            return ImageFont.load_default()


# ---------------------------------------------------------------------------
# 5. 워드 레벨 키워드 하이라이트 다이내믹 자막 렌더러 (Starisborn 74pt 볼드 규격 1:1 이식)
# ---------------------------------------------------------------------------
def render_highlighted_subtitle_png(text, highlight_word="", out_png="sub.png", font_path=FONT_MAIN,
                                    max_safe_w=940, default_fsize=72, highlight_color="#FFE600",
                                    highlight_keywords=None):
    """
    스타이즈본의 상위 1% 유튜브 지식 쇼츠 표준 74pt 대형 볼드 타이포그래피 1:1 렌더러.
    - 답답한 다크 글래스 박스/플레이트 전면 제거 (투명 배경 순수 타이포그래피)
    - 74pt Gmarket Sans TTF Bold + 7.0px 블랙 외곽선 + 4.0px 드롭 섀도우
    - 비비드 골드/네온 옐로우(#FFE600 / #FFD700) 키워드 하이라이트
    - 한글 발음(천구백십사년, 오백 달러) -> 아라비아 숫자/기호(1914년, 500달러) 자동 변환
    - 서술어/종결어미(습니다, 었습니다, 에게 등) 철저 배제 필터 탑재
    """
    dummy_img = Image.new("RGBA", (1080, 500), (0, 0, 0, 0))
    dummy_draw = ImageDraw.Draw(dummy_img)

    # 1. 숫자/날짜 정규화 및 정제
    clean_text = format_sub_display(text.strip())

    # 하이라이트 키워드 결정 (1순위: 대본 지정 키워드 1:1 매칭, 2순위: 청크 키워드 + 서술어 철저 배제)
    clean_kws = []
    if highlight_keywords:
        raw_list = [highlight_keywords] if isinstance(highlight_keywords, str) else list(highlight_keywords)
        for kw in raw_list:
            k_str = str(kw).strip(" .,?!'\"[]():;~")
            if k_str:
                clean_kws.append(k_str)
                fmt_k = format_sub_display(k_str)
                if fmt_k and fmt_k != k_str:
                    clean_kws.append(fmt_k)
    elif highlight_word:
        k_str = str(highlight_word).strip(" .,?!'\"[]():;~")
        if k_str and not is_stop_word(k_str):
            clean_kws.append(k_str)
            fmt_k = format_sub_display(k_str)
            if fmt_k and fmt_k != k_str and not is_stop_word(fmt_k):
                clean_kws.append(fmt_k)

    # 2. 폰트 크기 자동 조절 (기본 72pt, 2줄 초과 또는 너비 초과 시 62pt까지 미세 축소)
    cur_fsize = default_fsize
    words = clean_text.split()

    while cur_fsize > 58:
        font = get_sub_font(cur_fsize, font_path)
        lines = []
        cur_l = []
        for w in words:
            cand = " ".join(cur_l + [w])
            bb = dummy_draw.textbbox((0, 0), cand, font=font)
            if (bb[2] - bb[0]) > max_safe_w and cur_l:
                lines.append(cur_l)
                cur_l = [w]
            else:
                cur_l.append(w)
        if cur_l:
            lines.append(cur_l)

        if len(lines) <= 2:
            max_line_w = max((dummy_draw.textbbox((0, 0), " ".join(l), font=font)[2] -
                              dummy_draw.textbbox((0, 0), " ".join(l), font=font)[0]) for l in lines)
            if max_line_w <= max_safe_w:
                break
        cur_fsize -= 2

    font = get_sub_font(cur_fsize, font_path)

    # 최종 라인 구성
    lines = []
    cur_l = []
    for w in words:
        cand = " ".join(cur_l + [w])
        bb = dummy_draw.textbbox((0, 0), cand, font=font)
        if (bb[2] - bb[0]) > max_safe_w and cur_l:
            lines.append(cur_l)
            cur_l = [w]
        else:
            cur_l.append(w)
    if cur_l:
        lines.append(cur_l)

    line_step = cur_fsize + 20

    # 3. 라인별 메트릭 측정
    line_metrics = []
    bbs = []
    for i, l_words in enumerate(lines):
        l_str = " ".join(l_words)
        bb = dummy_draw.textbbox((0, i * line_step), l_str, font=font)
        lw = bb[2] - bb[0]
        line_metrics.append((l_words, lw))
        bbs.append(bb)

    vis_top = min(b[1] for b in bbs)
    vis_bottom = max(b[3] for b in bbs)
    vis_h = vis_bottom - vis_top

    canvas_w = 1080
    canvas_h = max(260, vis_h + 60)

    target_vis_top = (canvas_h - vis_h) // 2
    y_offset = target_vis_top - vis_top

    # 투명 캔버스 (다크 글래스 박스 없음!)
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    space_w = dummy_draw.textbbox((0, 0), " ", font=font)[2] - dummy_draw.textbbox((0, 0), " ", font=font)[0]

    # 골드 하이라이트 컬러 파싱
    if isinstance(highlight_color, str):
        if highlight_color.startswith("#"):
            hc = highlight_color.lstrip("#")
            hl_rgba = tuple(int(hc[i:i+2], 16) for i in (0, 2, 4)) + (255,)
        else:
            hl_rgba = (255, 230, 0, 255)
    else:
        hl_rgba = highlight_color

    # 4. 2-Pass 렌더링: Pass 1 드롭 섀도우 (4.0px), Pass 2 본문 텍스트 (7.0px 블랙 스트로크)
    for pass_mode in ("shadow", "main"):
        for i, (l_words, lw) in enumerate(line_metrics):
            x_cursor = (canvas_w - lw) // 2
            y_cursor = y_offset + i * line_step

            for w_idx, word in enumerate(l_words):
                # 하이라이트 키워드 부분 일치 정밀 분할 (조사/어미 분리 렌더링)
                clean_word = re.sub(r'[,.!?\'"“”~]', '', word)
                matched_kw = None
                for kw in clean_kws:
                    if kw and kw in clean_word and not is_stop_word(kw):
                        matched_kw = kw
                        break

                if matched_kw:
                    idx = word.find(matched_kw)
                    if idx != -1:
                        p1 = word[:idx]
                        p_kw = word[idx:idx + len(matched_kw)]
                        p2 = word[idx + len(matched_kw):]
                        sub_parts = []
                        if p1:
                            sub_parts.append((p1, False))
                        sub_parts.append((p_kw, True))
                        if p2:
                            sub_parts.append((p2, False))
                    else:
                        sub_parts = [(word, False)]
                else:
                    sub_parts = [(word, False)]

                for part_text, is_hl in sub_parts:
                    p_box = dummy_draw.textbbox((0, 0), part_text, font=font)
                    p_w = p_box[2] - p_box[0]

                    if pass_mode == "shadow":
                        # Starisborn 4.0px 드롭 섀도우
                        draw.text(
                            (x_cursor + 4, y_cursor + 4), part_text, font=font,
                            fill=(0, 0, 0, 220),
                            stroke_width=6, stroke_fill=(0, 0, 0, 220)
                        )
                    else:
                        # Starisborn 74pt 볼드 텍스트 + 7.0px 블랙 외곽선
                        fill_col = hl_rgba if is_hl else (255, 255, 255, 255)
                        draw.text(
                            (x_cursor, y_cursor), part_text, font=font,
                            fill=fill_col,
                            stroke_width=7, stroke_fill=(0, 0, 0, 255)
                        )

                    x_cursor += p_w

                x_cursor += space_w

    img.save(out_png, "PNG")
    return out_png


# ---------------------------------------------------------------------------
# 6. ASS 타임코드 포맷팅 및 파일 생성 (네이티브 ASS 지원)
# ---------------------------------------------------------------------------
def format_ass_time(s):
    """초 단위를 ASS 타임코드 포맷(h:mm:ss.cs)으로 변환."""
    cs = int(round((s % 1) * 100))
    if cs >= 100:
        s += 1
        cs = 0
    return f"{int(s // 3600):d}:{int((s % 3600) // 60):02d}:{int(s % 60):02d}.{cs:02d}"


def build_pro_ass_file(scenes, analyzed_scenes, durations, ass_path, offset=0.0, wav_paths=None, font_name="Gmarket Sans TTF"):
    """스타이즈본 규격 듀얼 레이어 ASS 자막 파일 생성 (Gmarket Sans TTF, 세이프존 MarginV=480)."""
    header = f"""[Script Info]
Title: History Shorts Dynamic Subtitle
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TopChapter, {font_name} Bold, 60, &H0000E6FF, &H00000000, &H00000000, &H00000000, 0, 0, 0, 0, 100, 100, 0, 0, 1, 6.0, 3.5, 8, 40, 40, 230, 1
Style: DynamicSub, {font_name} Bold, 74, &H00FFFFFF, &H00000000, &H00000000, &H00000000, 0, 0, 0, 0, 100, 100, 0, 0, 1, 7.0, 4.0, 2, 50, 50, 480, 1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    current_time = offset
    analyzed_map = {s["scene_number"]: s["chunks"] for s in analyzed_scenes}

    for sc, duration in zip(scenes, durations):
        s_no = sc.get("scene_number", 1)
        scene_start = current_time
        scene_end = current_time + duration

        caption = format_sub_display(sc.get("image_caption") or sc.get("display_title", ""))
        if caption:
            start_str = format_ass_time(scene_start)
            end_str = format_ass_time(scene_end)
            events.append(f"Dialogue: 1,{start_str},{end_str},TopChapter,,0,0,0,,{s_no:02d}  {caption}")

        chunks = sc.get("chunks") or analyzed_map.get(s_no, [])
        if not chunks:
            chunks = rule_based_chunking(sc.get("script", ""))

        # 1. Google Cloud TTS 실측 Timepoints 우선 적용
        timings = []
        if chunks and len(chunks) > 0 and "start" in chunks[0]:
            timings = [(c, float(c["start"]), float(c["end"])) for c in chunks]
        else:
            tp_loaded = False
            if wav_paths and s_no in wav_paths and os.path.exists(wav_paths[s_no]):
                audio_p = wav_paths[s_no]
                cand_tps = [
                    os.path.join(os.path.dirname(audio_p), f"timepoints_scene{s_no}.json"),
                    os.path.join(os.path.dirname(os.path.dirname(audio_p)), f"timepoints_scene{s_no}.json")
                ]
                for tp_f in cand_tps:
                    if os.path.exists(tp_f):
                        try:
                            with open(tp_f, "r", encoding="utf-8") as f_tp:
                                tp_d = json.load(f_tp)
                                timings = [(c, float(c["start"]), float(c["end"])) for c in tp_d.get("chunks", [])]
                                tp_loaded = True
                                break
                        except Exception:
                            pass
            if not tp_loaded:
                lead_in = 0.0
                if wav_paths and s_no in wav_paths and os.path.exists(wav_paths[s_no]):
                    lead_in = get_audio_voice_activity(wav_paths[s_no])
                timings = calculate_weighted_timings(chunks, duration, lead_in=lead_in)

        # 씬 지정 키워드
        raw_kws = sc.get("highlight_keywords", [])
        if isinstance(raw_kws, str):
            raw_kws = [raw_kws]
        elif not isinstance(raw_kws, list):
            raw_kws = []

        for c_dict, c_st, c_en in timings:
            abs_st = scene_start + c_st
            abs_en = scene_start + c_en
            c_text = format_sub_display(c_dict["text"].strip())
            c_highlight = c_dict.get("highlight", "").strip()

            styled_text = c_text
            applied_highlight = False

            # 1순위: 대본 키워드 매칭
            for kw in raw_kws:
                kw_clean = str(kw).strip(" .,?!'\"")
                for cand in [kw_clean, format_sub_display(kw_clean)]:
                    if cand and cand in styled_text:
                        replacement = rf"{{\c&H0000E6FF&}}{cand}{{\c&H00FFFFFF&}}"
                        styled_text = styled_text.replace(cand, replacement, 1)
                        applied_highlight = True
                        break
                if applied_highlight:
                    break

            # 2순위: 청크 키워드 매칭 (서술어 배제)
            if not applied_highlight and c_highlight:
                cand = format_sub_display(c_highlight.strip(" .,?!'\""))
                if len(cand) >= 2 and not any(cand.endswith(se) for se in STOP_ENDINGS):
                    if cand in styled_text:
                        replacement = rf"{{\c&H0000E6FF&}}{cand}{{\c&H00FFFFFF&}}"
                        styled_text = styled_text.replace(cand, replacement, 1)

            st_str = format_ass_time(abs_st)
            et_str = format_ass_time(abs_en)
            events.append(f"Dialogue: 0,{st_str},{et_str},DynamicSub,,0,0,0,,{styled_text}")

        current_time = scene_end

    full_ass = header + "\n".join(events)
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(full_ass)
    return ass_path
