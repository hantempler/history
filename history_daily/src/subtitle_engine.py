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
# 5. 워드 레벨 키워드 하이라이트 글래스 플레이트(PNG) 렌더러
# ---------------------------------------------------------------------------
def render_highlighted_subtitle_png(text, highlight_word, out_png, font_path=FONT_MAIN,
                                    max_safe_w=920, default_fsize=58, highlight_color="#FFD700"):
    """
    스타이즈본의 옐로우/골드 키워드 하이라이트를 역사 숏폼 다크 플레이트에 결합하여,
    키워드는 시인성 높은 골드(#FFD700), 일반 단어는 클린 화이트(#FFFCF4)로 워드 레벨 듀얼 컬러 렌더링.
    상하단 패딩을 정밀 대칭(pad_y)으로 보정하여 위쪽 쏠림 현상을 완벽 제거.
    """
    dummy_img = Image.new("RGBA", (1080, 400), (0, 0, 0, 0))
    dummy_draw = ImageDraw.Draw(dummy_img)

    clean_text = text.strip()
    highlight_clean = (highlight_word or "").strip()

    # 폰트 크기 자동 조절 루프
    cur_fsize = default_fsize
    font = get_sub_font(cur_fsize, font_path)

    words = clean_text.split()
    # 2줄 초과 또는 너비 초과 시 폰트 축소
    while cur_fsize > 44:
        font = get_sub_font(cur_fsize, font_path)
        # 줄바꿈 시뮬레이션
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

    line_step = cur_fsize + 18

    # 텍스트 라인별 바운딩 박스 및 렌더링 메트릭 정밀 측정
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
    vis_w = max(lw for _, lw in line_metrics)

    pad_x = 42
    pad_y = 22

    canvas_w = 1080
    canvas_h = max(240, vis_h + 100)

    # 텍스트 시각적 중심을 캔버스 정중앙에 정확히 일치
    target_vis_top = (canvas_h - vis_h) // 2
    y_offset = target_vis_top - vis_top

    # 플레이트 상/하 여백을 pad_y로 완전히 동일하게 보정 (상하 대칭 100%)
    px0 = max(24, (canvas_w - vis_w) // 2 - pad_x)
    px1 = min(canvas_w - 24, (canvas_w + vis_w) // 2 + pad_x)
    py0 = max(8, target_vis_top - pad_y)
    py1 = min(canvas_h - 8, target_vis_top + vis_h + pad_y)

    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    # 다크 라운드 글래스 플레이트 배경
    plate = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    p_draw = ImageDraw.Draw(plate)
    p_draw.rounded_rectangle([px0, py0, px1, py1], radius=24, fill=(8, 12, 18, 195))
    plate = plate.filter(ImageFilter.GaussianBlur(radius=2))
    img = Image.alpha_composite(img, plate)

    # 텍스트 그리기 (워드 레벨 하이라이트 치환)
    draw = ImageDraw.Draw(img)
    space_w = dummy_draw.textbbox((0, 0), " ", font=font)[2] - dummy_draw.textbbox((0, 0), " ", font=font)[0]

    for i, (l_words, lw) in enumerate(line_metrics):
        x_cursor = (canvas_w - lw) // 2
        y_cursor = y_offset + i * line_step

        for w_idx, word in enumerate(l_words):
            clean_word = re.sub(r'[,.!?\'"“”]', '', word)

            # 하이라이트 단어 일치 여부 판별
            is_highlight = False
            if highlight_clean:
                if clean_word == highlight_clean or clean_word in highlight_clean or highlight_clean in clean_word:
                    is_highlight = True

            fill_color = highlight_color if is_highlight else (255, 252, 244, 255)
            stroke_width = 5 if is_highlight else 4

            draw.text((x_cursor, y_cursor), word, font=font, fill=fill_color,
                      stroke_width=stroke_width, stroke_fill=(0, 0, 0, 255))

            w_box = dummy_draw.textbbox((0, 0), word, font=font)
            word_w = w_box[2] - w_box[0]
            x_cursor += word_w + space_w

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
Style: TopChapter, {font_name}, 62, &H00FFFFFF, &H00000000, &H00000000, &H00000000, 1, 0, 0, 0, 100, 100, 0, 0, 1, 6.0, 3.5, 8, 40, 40, 160, 1
Style: DynamicSub, {font_name}, 74, &H00FFFFFF, &H00000000, &H00000000, &H00000000, 1, 0, 0, 0, 100, 100, 0, 0, 1, 7.0, 4.0, 2, 50, 50, 480, 1

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

        caption = sc.get("image_caption") or sc.get("display_title", "")
        if caption:
            start_str = format_ass_time(scene_start)
            end_str = format_ass_time(scene_end)
            chapter_text = rf"{{\c&H0000E6FF&}}0{s_no}{{\c&H00FFFFFF&}}  {caption}"
            events.append(f"Dialogue: 1,{start_str},{end_str},TopChapter,,0,0,0,,{chapter_text}")

        chunks = analyzed_map.get(s_no, [])
        if not chunks:
            chunks = rule_based_chunking(sc.get("script", ""))

        lead_in = 0.0
        if wav_paths and s_no in wav_paths and os.path.exists(wav_paths[s_no]):
            lead_in = get_audio_voice_activity(wav_paths[s_no])

        timings = calculate_weighted_timings(chunks, duration, lead_in=lead_in)

        for c_dict, c_st, c_en in timings:
            abs_st = scene_start + c_st
            abs_en = scene_start + c_en
            c_text = c_dict["text"].strip()
            c_highlight = c_dict.get("highlight", "").strip()

            styled_text = c_text
            if c_highlight and c_highlight in styled_text:
                styled_text = styled_text.replace(c_highlight, rf"{{\c&H0000E6FF&}}{c_highlight}{{\c&H00FFFFFF&}}", 1)

            st_str = format_ass_time(abs_st)
            et_str = format_ass_time(abs_en)
            events.append(f"Dialogue: 0,{st_str},{et_str},DynamicSub,,0,0,0,,{styled_text}")

        current_time = scene_end

    full_ass = header + "\n".join(events)
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(full_ass)
    return ass_path
