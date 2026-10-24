import os
import sys
import json
import re
import subprocess
import shutil
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import imageio_ffmpeg

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_DIR = os.path.dirname(BASE_DIR)
CONFIG_DIR = os.path.join(BASE_DIR, 'config')
CRED_PATH = os.path.join(CONFIG_DIR, 'application_default_credentials.json')
if os.path.exists(CRED_PATH):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CRED_PATH

import io

FONT_PATH = os.path.join(CONFIG_DIR, 'GmarketSansTTFBold.ttf')
with open(FONT_PATH, 'rb') as _f:
    _FONT_BYTES = _f.read()

def get_font(size):
    return ImageFont.truetype(io.BytesIO(_FONT_BYTES), size)

_sys_ffmpeg = shutil.which("ffmpeg")
FFMPEG = _sys_ffmpeg if _sys_ffmpeg else imageio_ffmpeg.get_ffmpeg_exe()

CANVAS_W, CANVAS_H = 1080, 1920
FPS = 24
BGM_DIR = os.path.join(BASE_DIR, 'assets', 'bgm')

CORNER_COLOR_MAP = {
    "역사 딥다이브": (229, 169, 60),   # 샴페인 골드
    "미스터리 파일": (138, 79, 255),   # 딥 바이올렛
    "실록 오늘": (46, 204, 113),       # 단청 비취 그린
    "전술·전쟁사": (231, 76, 60),      # 카민 레드
    "인물 60초": (243, 156, 18),       # 웜 앰버
    "역사 VS": (52, 152, 219),         # 일렉트릭 블루
    "시국 평행이론": (149, 165, 166),   # 네오 실버
    "1분 타임머신": (229, 169, 60)      # 샴페인 골드 (기본)
}


def get_audio_duration(path: str) -> float:
    cmd = [FFMPEG, "-i", path]
    p = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", p.stderr)
    if m:
        h, m_val, s = m.groups()
        return int(h) * 3600 + int(m_val) * 60 + float(s)
    return 5.0


def load_and_fill_fullscreen(img_path):
    if not img_path or not os.path.exists(img_path):
        fallback_dirs = [
            os.path.join(BASE_DIR, 'assets'),
            os.path.join(WORKSPACE_DIR, 'history_daily', 'assets')
        ]
        for f_dir in fallback_dirs:
            for fb_name in ["dark_paper_bg.jpg", "vintage_bg.jpg", "stone_bg.jpg"]:
                fb_p = os.path.join(f_dir, fb_name)
                if os.path.exists(fb_p):
                    img_path = fb_p
                    break
            if img_path and os.path.exists(img_path):
                break

    if not img_path or not os.path.exists(img_path):
        return Image.new("RGBA", (CANVAS_W, CANVAS_H), (20, 24, 32, 255))

    raw_im = Image.open(img_path).convert("RGB")
    rw, rh = raw_im.size
    scale = max(CANVAS_W / rw, CANVAS_H / rh)
    sw, sh = int(rw * scale), int(rh * scale)
    bg_scaled = raw_im.resize((sw, sh), Image.Resampling.LANCZOS)
    cx = (sw - CANVAS_W) // 2
    cy = (sh - CANVAS_H) // 2
    cropped = bg_scaled.crop((cx, cy, cx + CANVAS_W, cy + CANVAS_H))
    cropped = ImageEnhance.Color(cropped).enhance(1.03)
    cropped = ImageEnhance.Contrast(cropped).enhance(1.02)
    return cropped.convert("RGBA")


def apply_top_soft_gradient(img):
    w, h = img.size
    grad = Image.new("L", (1, h), 0)
    pix = grad.load()
    for y in range(h):
        if y < 480:
            pix[0, y] = int(220 * ((1.0 - y / 480.0) ** 1.3))
        else:
            pix[0, y] = 0
    grad = grad.resize((w, h))
    shade = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shade.putalpha(grad)
    return Image.alpha_composite(img, shade)


def apply_intro_gradient(img):
    w, h = img.size
    grad = Image.new("L", (1, h), 0)
    pix = grad.load()
    for y in range(h):
        ratio = y / max(1, h - 1)
        if ratio < 0.40:
            pix[0, y] = int(220 * (1 - ratio / 0.40))
        elif ratio > 0.55:
            pix[0, y] = int(225 * ((ratio - 0.55) / 0.45))
        else:
            pix[0, y] = 120
    grad = grad.resize((w, h))
    shade = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shade.putalpha(grad)
    return Image.alpha_composite(img, shade)


# -------------------------------------------------------------
# Tofu(글리프 깨짐) 방지 정제 유틸리티
# -------------------------------------------------------------
def sanitize_tofu(text):
    if not text:
        return ""
    # 모든 이모지 및 특수 기호(BMP 및 SMP 전체) 완벽 제거
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'[\u2300-\u23ff\u2600-\u27bf\u2b00-\u2bff]', '', text)
    replacements = {
        '\u2022': ' ', '\u2023': ' ', '\u25E6': ' ', '\u2043': ' ', '\u2219': ' ',
        '“': '"', '”': '"', '‘': "'", '’': "'",
        '—': '-', '–': '-', '·': ' ', '…': '...',
        '\uFFFD': ' ', '☒': '', '□': '', '▼': '', '▲': '',
        '🏛': '', '⏳': '', '📜': '', '⚖': '', '💬': '', '🔔': '', '⚡': ''
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.strip()


# -------------------------------------------------------------
# [0~4.2초] 표지 인트로 영상 (넷플릭스/방송 다큐멘터리 스타일 무비 포스터 타이포그래피, 박스/알약 0%)
# -------------------------------------------------------------
def render_intro_cover_image(bg_path, header_str, highlight_cat, main_title, why_title=None, why_desc=None, target_date_str=None, kicker_str=None, lang="ko"):
    base_img = load_and_fill_fullscreen(bg_path)
    
    # 날짜 분석
    month_num, day_num = 10, 24
    if target_date_str:
        digits = re.sub(r'\D', '', target_date_str)
        if len(digits) >= 8:
            month_num = int(digits[4:6])
            day_num = int(digits[6:8])
    else:
        m_match = re.search(r'(\d{1,2})월\s*(\d{1,2})일', header_str)
        if m_match:
            month_num = int(m_match.group(1))
            day_num = int(m_match.group(2))

    # 부드러운 연속 시네마틱 비네팅 (계단/경계선 없는 완벽한 부드러운 감쇠)
    scrim = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 45))
    s_draw = ImageDraw.Draw(scrim)
    for y in range(650):
        ratio = 1.0 - (y / 650.0)
        a = int(170 * (ratio ** 1.8))
        s_draw.line([(0, y), (CANVAS_W, y)], fill=(0, 0, 0, 45 + a))
    for y in range(1100, CANVAS_H):
        ratio = (y - 1100) / float(CANVAS_H - 1100)
        a = int(180 * (ratio ** 1.5))
        s_draw.line([(0, y), (CANVAS_W, y)], fill=(0, 0, 0, 45 + a))

    base_img = Image.alpha_composite(base_img, scrim)
    draw = ImageDraw.Draw(base_img)

    f_top = get_font(30)
    f_main = get_font(68)
    f_sub = get_font(28)
    f_cue = get_font(24)

    # 1. 상단 미니멀 날짜/브랜딩 (알약/박스 없음!)
    month_names_en = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
                      "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"]
    if lang == "en":
        m_name = month_names_en[max(0, min(11, month_num - 1))]
        top_txt = f"{m_name} {day_num}  |  ON THIS DAY"
    else:
        top_txt = f"{month_num}월 {day_num}일  |  역사 속 오늘"
    tb = draw.textbbox((0, 0), top_txt, font=f_top)
    draw.text(((CANVAS_W - (tb[2] - tb[0])) // 2, 230), top_txt, font=f_top, fill=(255, 215, 0), stroke_width=3, stroke_fill="black")

    # 2. 메인 질문 (영화 포스터급 볼드 타이포, 박스 없음!)
    clean_title = sanitize_tofu(main_title.strip())
    words = clean_title.split()
    lines, cur = [], []
    for w in words:
        cand = " ".join(cur + [w])
        bb = draw.textbbox((0, 0), cand, font=f_main)
        if (bb[2] - bb[0]) > 880 and cur:
            lines.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))

    start_y = 510 if len(lines) <= 2 else 460
    step_y = 100
    for idx_l, l_str in enumerate(lines[:3]):
        b = draw.textbbox((0, 0), l_str, font=f_main)
        lx = (CANVAS_W - (b[2] - b[0])) // 2
        ly = start_y + idx_l * step_y
        draw.text((lx + 3, ly + 3), l_str, font=f_main, fill=(0, 0, 0, 240))
        fill_c = (255, 255, 255) if idx_l == 0 else (255, 215, 0)
        draw.text((lx, ly), l_str, font=f_main, fill=fill_c, stroke_width=4, stroke_fill="black")

    # 3. 얇은 골드 액센트 분리선
    div_y = start_y + len(lines[:3]) * step_y + 25
    draw.line([(380, div_y), (700, div_y)], fill=(229, 169, 60, 220), width=2)

    # 4. 서브 훅 설명 (충분한 좌우 여백과 줄바꿈)
    why_text = sanitize_tofu(why_desc or why_title or ("The turning point that shaped modern history" if lang == "en" else "주권국가 체제의 초석을 다진 베스트팔렌 조약의 진실"))
    w_words = why_text.split()
    w_lines, w_cur = [], []
    for w in w_words:
        cand = " ".join(w_cur + [w])
        bb = draw.textbbox((0, 0), cand, font=f_sub)
        if (bb[2] - bb[0]) > 840 and w_cur:
            w_lines.append(" ".join(w_cur))
            w_cur = [w]
        else:
            w_cur.append(w)
    if w_cur:
        w_lines.append(" ".join(w_cur))

    sub_y = div_y + 35
    for wl in w_lines[:2]:
        sb = draw.textbbox((0, 0), wl, font=f_sub)
        draw.text(((CANVAS_W - (sb[2] - sb[0])) // 2, sub_y), wl, font=f_sub, fill=(240, 245, 255), stroke_width=2, stroke_fill="black")
        sub_y += 42

    # 5. 하단 탐구 유도 문구
    cue = "EXPLORE TODAY'S HISTORY" if lang == "en" else "오늘의 역사 깊이보기"
    cb = draw.textbbox((0, 0), cue, font=f_cue)
    draw.text(((CANVAS_W - (cb[2] - cb[0])) // 2, sub_y + 55), cue, font=f_cue, fill=(229, 169, 60), stroke_width=2, stroke_fill="black")

    return base_img


# -------------------------------------------------------------
# [본문용] 방송사 다큐멘터리 스타일 상단 통합 헤더 (알약 0%, 사료 상단 배치 100% 가시성)
# -------------------------------------------------------------
def draw_cinematic_scene_header(draw, base_img, date_str, scene_title, archive_caption=None, credit_str=None, image_type="archive", lang="ko"):
    font_date = get_font(28)
    font_title = get_font(48)
    font_arc = get_font(24)

    # 1. 상단 날짜 (28pt 골드, 알약 없음!)
    fallback_date = "ON THIS DAY" if lang == "en" else "오늘의 역사"
    clean_date = sanitize_tofu(date_str) if date_str else fallback_date
    db = draw.textbbox((0, 0), clean_date, font=font_date)
    draw.text(((CANVAS_W - (db[2] - db[0])) // 2, 155), clean_date, font=font_date, fill=(255, 215, 0), stroke_width=3, stroke_fill="black")

    # 2. 씬 메인 소제목 (48pt Bold White with drop shadow)
    clean_title = sanitize_tofu(scene_title.strip())
    tb = draw.textbbox((0, 0), clean_title, font=font_title)
    tx = (CANVAS_W - (tb[2] - tb[0])) // 2
    ty = 210
    draw.text((tx + 2, ty + 2), clean_title, font=font_title, fill=(0, 0, 0, 240))
    draw.text((tx, ty), clean_title, font=font_title, fill=(255, 255, 255), stroke_width=4, stroke_fill='black')

    # 3. [핵심 개선] 사료 정보 상단 배치 (100% 식별 보장, 알약 없음)
    if archive_caption and archive_caption.strip() and archive_caption.strip() != clean_title:
        clean_cap = sanitize_tofu(archive_caption.strip())
        src_suffix = ""
        is_ai = (image_type == "ai_generated") or (credit_str and ("Vertex AI" in credit_str or "AI 생성" in credit_str or "AI" in credit_str))
        
        if lang == "en":
            if is_ai:
                prefix = "AI GENERATED"
                src_suffix = " (Vertex AI)"
            else:
                prefix = "ARCHIVE"
                src_suffix = " (Wikimedia Commons)"
        else:
            if is_ai:
                prefix = "AI 생성"
                if credit_str and "Vertex AI" in credit_str:
                    src_suffix = " (Vertex AI)"
                else:
                    src_suffix = " (AI 복원)"
            else:
                prefix = "사료"
                if credit_str:
                    if "위키미디어" in credit_str:
                        src_suffix = " (위키미디어 커먼즈)"
                    elif "연방기록관" in credit_str:
                        src_suffix = " (독일 연방기록관)"

        arc_txt = f"{prefix} : {clean_cap}{src_suffix}"
        ab = draw.textbbox((0, 0), arc_txt, font=font_arc)
        aw = ab[2] - ab[0]
        ax = (CANVAS_W - aw) // 2
        ay = 280

        # 단정한 직사각형 다크 틴트 스트립 (알약 X, 모서리 둥글지 않음)
        draw.rectangle([ax - 16, ay - 3, ax + aw + 16, ay + 31], fill=(10, 14, 22, 175))
        draw.text((ax, ay), arc_txt, font=font_arc, fill=(255, 235, 185) if not is_ai else (175, 225, 255), stroke_width=2, stroke_fill='black')
        return ay + 35

    return ty + 60


# -------------------------------------------------------------
# 자막 청크 분할 및 타이밍 산출
# -------------------------------------------------------------
def chunk_text_smart(text, max_length=12):
    text = (text or "").replace('\n', ' ').strip()
    if not text:
        return []

    sentences = [s.strip() for s in re.split(r'(?<=[.!?…。！？])\s*', text) if s.strip()]

    def wrap_words(words, width=13):
        lines, cur = [], []
        for w in words:
            if sum(len(x) for x in cur) + len(cur) + len(w) > width:
                if cur:
                    lines.append(" ".join(cur))
                cur = [w]
            else:
                cur.append(w)
        if cur:
            lines.append(" ".join(cur))
        return lines

    chunks = []
    for s in sentences:
        words = s.split()
        s_lines = wrap_words(words, max_length)

        i = 0
        while i < len(s_lines):
            if i == len(s_lines) - 1 and len(s_lines[i]) < 8 and chunks:
                prev = chunks[-1]
                prev_lines = prev.split("\n")
                if len(prev_lines) == 1:
                    chunks[-1] = prev + "\n" + s_lines[i]
                else:
                    chunks.append(s_lines[i])
                i += 1
            elif i + 1 < len(s_lines):
                chunks.append(s_lines[i] + "\n" + s_lines[i + 1])
                i += 2
            else:
                chunks.append(s_lines[i])
                i += 1

    cleaned_chunks = []
    for c in chunks:
        c_clean = c.strip()
        if len(c_clean) <= 7 and ' ' not in c_clean and cleaned_chunks:
            prev = cleaned_chunks[-1]
            if "\n" not in prev:
                cleaned_chunks[-1] = prev + "\n" + c_clean
            else:
                cleaned_chunks[-1] = prev + " " + c_clean
        else:
            cleaned_chunks.append(c_clean)

    return cleaned_chunks


def calculate_subtitle_timings(chunks, total_duration):
    if not chunks:
        return []
    lengths = [max(1, len(re.sub(r'\s+', '', c))) for c in chunks]
    total_chars = sum(lengths)
    timings = []
    curr_time = 0.0
    for chunk, char_len in zip(chunks, lengths):
        dur = total_duration * (char_len / total_chars)
        st = curr_time
        en = min(total_duration, curr_time + dur)
        timings.append((chunk, round(st, 3), round(en, 3)))
        curr_time = en
    return timings


# -------------------------------------------------------------
# 자막 가독성 카드 (다크 라운드 플레이트)
# -------------------------------------------------------------
def render_subtitle_png(text, out_png):
    max_safe_w = 900
    default_fsize = 58
    dummy_img = Image.new("RGBA", (1080, 400), (0, 0, 0, 0))
    dummy_draw = ImageDraw.Draw(dummy_img)

    raw_lines = text.strip().split("\n")
    font = ImageFont.truetype(FONT_PATH, default_fsize)

    wrapped_lines = []
    for line in raw_lines:
        words = line.split()
        cur = []
        for w in words:
            test_line = " ".join(cur + [w])
            bbox = dummy_draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] > max_safe_w and cur:
                wrapped_lines.append(" ".join(cur))
                cur = [w]
            else:
                cur.append(w)
        if cur:
            wrapped_lines.append(" ".join(cur))

    final_fsize = default_fsize
    while final_fsize > 46:
        f = ImageFont.truetype(FONT_PATH, final_fsize)
        too_wide = False
        for wl in wrapped_lines:
            bb = dummy_draw.textbbox((0, 0), wl, font=f)
            if bb[2] - bb[0] > max_safe_w:
                too_wide = True
                break
        if not too_wide:
            font = f
            break
        final_fsize -= 2
        font = f

    spacing = 16
    clean_text = "\n".join(wrapped_lines)

    bbox = dummy_draw.multiline_textbbox((0, 0), clean_text, font=font, spacing=spacing)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    canvas_w = 1080
    canvas_h = max(280, th + 80)
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    x = (canvas_w - tw) // 2
    y = (canvas_h - th) // 2

    pad_x, pad_y = 44, 22
    px0 = max(20, x - pad_x)
    py0 = max(5, y - pad_y)
    px1 = min(canvas_w - 20, x + tw + pad_x)
    py1 = min(canvas_h - 5, y + th + pad_y)

    plate = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    p_draw = ImageDraw.Draw(plate)
    p_draw.rounded_rectangle([px0, py0, px1, py1], radius=24, fill=(8, 12, 18, 185))
    plate = plate.filter(ImageFilter.GaussianBlur(radius=2))
    img = Image.alpha_composite(img, plate)

    draw = ImageDraw.Draw(img)
    draw.multiline_text((x, y), clean_text, font=font, fill=(255, 252, 244, 255),
                        align="center", spacing=spacing, stroke_width=4, stroke_fill='black')
    img.save(out_png, "PNG")


def draw_credit_safe_zone(draw, credit_str, caption_str=None, image_type="archive", start_y=None, center=True):
    if not credit_str and not caption_str:
        return
    if start_y is not None:
        cur_y = start_y
        if caption_str:
            font_cap = ImageFont.truetype(FONT_PATH, 25)
            prefix = "사료: " if image_type == "archive" else "고증 복원: "
            cap_full = f"{prefix}{caption_str}"
            cb = draw.textbbox((0, 0), cap_full, font=font_cap)
            cw = cb[2] - cb[0]
            cx = (CANVAS_W - cw) // 2 if center else 55
            # 가독성 극대화를 위한 다크 아웃라인 & 섀도우
            draw.text((int(cx + 2), int(cur_y + 2)), cap_full, font=font_cap, fill=(0, 0, 0, 220))
            draw.text((int(cx), int(cur_y)), cap_full, font=font_cap, fill=(255, 238, 185), stroke_width=3, stroke_fill='black')
            cur_y += 36

def draw_credit_safe_zone(draw, credit_str, caption_str=None, image_type="archive", start_y=None, center=True):
    # 크레딧은 화면 최하단(y=1885)에 은은하게 작게 표시하여 중앙 시선 방해를 완전히 배제
    if credit_str:
        font_credit = ImageFont.truetype(FONT_PATH, 18)
        cb = draw.textbbox((0, 0), credit_str, font=font_credit)
        cw = cb[2] - cb[0]
        draw.text((int((CANVAS_W - cw) // 2), 1885), credit_str, font=font_credit, fill=(180, 195, 215, 140))


def apply_cinematic_vignette(im):
    w, h = im.size
    grad = Image.new("L", (1, h), 0)
    pix = grad.load()
    for y in range(h):
        ratio = y / float(h)
        if ratio < 0.20:
            pix[0, y] = int(210 * (1.0 - ratio / 0.20))
        elif ratio > 0.65:
            pix[0, y] = int(240 * ((ratio - 0.65) / 0.35) ** 0.9)
        else:
            pix[0, y] = 85
    grad = grad.resize((w, h))
    shade = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shade.putalpha(grad)
    return Image.alpha_composite(im, shade)

def split_to_two_lines(text: str):
    text = sanitize_tofu(text.strip().replace("'", "").replace('"', "").replace("‘", "").replace("’", ""))
    words = text.split()
    if len(words) >= 4:
        mid = (len(words) + 1) // 2
        return " ".join(words[:mid]), " ".join(words[mid:])
    elif len(words) == 3:
        return " ".join(words[:2]), words[2]
    elif len(words) == 2:
        return words[0], words[1]
    return text, ""


# -------------------------------------------------------------
# -------------------------------------------------------------
# [아웃트로 피날레] 시네마틱 중앙 철학적 질문 (여운을 남기는 다큐 에필로그)
# -------------------------------------------------------------
def render_outro_finale_image(bg_path, credit_str, outro_debate=None, date_title_str=None, lang="ko"):
    base_img = load_and_fill_fullscreen(bg_path)
    base_img = base_img.filter(ImageFilter.GaussianBlur(radius=8))
    base_img = ImageEnhance.Brightness(base_img).enhance(0.38)
    scrim = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 160))
    base_img = Image.alpha_composite(base_img, scrim)
    draw = ImageDraw.Draw(base_img)

    f_top = get_font(32)
    f_q_main = get_font(46)
    f_q_sub = get_font(30)

    # 1. 텍스트 추출 및 정제
    top_txt = "QUESTIONS HISTORY LEFT BEHIND" if lang == "en" else "역사가 남긴 질문"

    if lang == "en":
        target_title = outro_debate.get("target_entity", "This historical event") if outro_debate else "This historical event"
        target_title = sanitize_tofu(target_title)
        qa1 = outro_debate.get("question_a_1", "A triumph of diplomacy") if outro_debate else "A triumph of diplomacy"
        qa2 = outro_debate.get("question_a_2", "what lessons does the past leave for us today?") if outro_debate else "what lessons does the past leave for us today?"
        q1 = f'"{qa1},' if not qa1.startswith('"') else qa1
        q2 = f'{qa2}"' if not qa2.endswith('"') else qa2
        ev_txt = f"{target_title} asks us today"
    else:
        target_title = outro_debate.get("target_entity", "역사의 순간") if outro_debate else "역사의 순간"
        target_title = sanitize_tofu(target_title)
        if outro_debate and "question_a_1" in outro_debate and "question_a_2" in outro_debate:
            qa1 = sanitize_tofu(outro_debate.get("question_a_1", ""))
            qa2 = sanitize_tofu(outro_debate.get("question_a_2", ""))
            q1 = f'"{qa1},' if not qa1.startswith('"') else qa1
            if qa2.endswith('"'):
                q2 = qa2
            elif qa2.endswith('?'):
                q2 = f'{qa2}"'
            elif any(qa2.endswith(end) for end in ['인가', '일까', '을까', '한가', '건가', '는가', '나요', '가요', '까요']):
                q2 = f'{qa2}?"'
            else:
                q2 = f'{qa2}이었을까요?"'
        elif outro_debate and "question_a_2" in outro_debate:
            q_cand = sanitize_tofu(outro_debate.get("question_a_2", ""))
            q1 = f'"{q_cand},'
            q2 = '역사는 우리에게 어떤 답을 남겼을까요?"'
        else:
            q1 = '"수백만의 피로 맺은 평화,'
            q2 = '과연 진정한 공존이란 무엇일까요?"'
        ev_txt = f"{target_title}이 오늘날 우리에게 묻습니다"

    # 텍스트 줄바꿈 (화면 너비 880px 제한)
    def wrap_text_lines(text_to_wrap, font, max_w=880):
        words = text_to_wrap.strip().split()
        res_lines, cur_l = [], []
        for w in words:
            cand = " ".join(cur_l + [w])
            bb = draw.textbbox((0, 0), cand, font=font)
            if (bb[2] - bb[0]) > max_w and cur_l:
                res_lines.append(" ".join(cur_l))
                cur_l = [w]
            else:
                cur_l.append(w)
        if cur_l:
            res_lines.append(" ".join(cur_l))
        return res_lines

    wrapped_lines = []
    for q_part in [q1, q2]:
        if q_part:
            wrapped_lines.extend(wrap_text_lines(q_part, f_q_main, max_w=880))

    cur_f_q = f_q_main
    step_q_y = 70
    if len(wrapped_lines) > 2:
        cur_f_q = get_font(38)
        step_q_y = 60
        wrapped_lines = []
        for q_part in [q1, q2]:
            if q_part:
                wrapped_lines.extend(wrap_text_lines(q_part, cur_f_q, max_w=880))

    # 2. 전체 블록 높이 계산 및 완벽한 수직 중앙 배치 (중앙 Y = 930)
    tb = draw.textbbox((0, 0), top_txt, font=f_top)
    top_h = tb[3] - tb[1]

    eb = draw.textbbox((0, 0), ev_txt, font=f_q_sub)
    ev_h = eb[3] - eb[1]

    gap_top_to_line = 18
    gap_line_to_q = 60
    q_total_h = len(wrapped_lines[:4]) * step_q_y
    gap_q_to_ev = 45

    total_block_h = top_h + gap_top_to_line + gap_line_to_q + q_total_h + gap_q_to_ev + ev_h

    # 9:16 모바일 쇼츠 시각적 황금 중앙 좌표 (약 930px)
    center_y = 930
    start_y = center_y - (total_block_h // 2)

    # 3. 렌더링: 상단 타이틀
    top_y = start_y
    draw.text(((CANVAS_W - (tb[2] - tb[0])) // 2, top_y), top_txt, font=f_top, fill=(255, 215, 0), stroke_width=3, stroke_fill="black")

    line_w = 120 if lang == "en" else 90
    line_y = top_y + top_h + gap_top_to_line
    draw.line([(CANVAS_W // 2 - line_w, line_y), (CANVAS_W // 2 + line_w, line_y)], fill=(229, 169, 60, 220), width=2)

    # 4. 렌더링: 중심 철학적 질문 (여운을 주는 다큐 에필로그 쿼트)
    start_q_y = line_y + gap_line_to_q
    for idx_l, l_txt in enumerate(wrapped_lines[:4]):
        qb = draw.textbbox((0, 0), l_txt, font=cur_f_q)
        draw.text(((CANVAS_W - (qb[2] - qb[0])) // 2, start_q_y + idx_l * step_q_y), l_txt, font=cur_f_q, fill=(255, 255, 255), stroke_width=4, stroke_fill="black")

    # 5. 렌더링: 역사적 사건 귀속 및 화두 제시
    ev_y = start_q_y + q_total_h + gap_q_to_ev - 15
    draw.text(((CANVAS_W - (eb[2] - eb[0])) // 2, ev_y), ev_txt, font=f_q_sub, fill=(225, 235, 245), stroke_width=2, stroke_fill="black")

    return base_img


# -------------------------------------------------------------
# 본문 씬 렌더러
# -------------------------------------------------------------
def render_body_scene_chunk(bg_path, corner_name, date_title, credit_str, tts_text, audio_path, duration, out_chunk_mp4, temp_dir, zoom_in=True, subtitle_cards=None, caption_str=None, image_type="archive", dynamic_chunks=None, scene_title=None, lang="ko"):
    os.makedirs(temp_dir, exist_ok=True)
    frames = max(1, int(round(duration * FPS)))

    base_img = load_and_fill_fullscreen(bg_path)
    base_img = apply_top_soft_gradient(base_img)

    # 하단 자막 영역 소프트 다크 스크림 그라데이션 (가독성 100% 보장)
    scrim = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(scrim)
    for sy in range(1200, CANVAS_H):
        alpha = int(120 * ((sy - 1200) / (CANVAS_H - 1200)) ** 1.2)
        s_draw.line([(0, sy), (CANVAS_W, sy)], fill=(0, 0, 0, alpha))
    base_img = Image.alpha_composite(base_img, scrim)

    draw = ImageDraw.Draw(base_img)
    actual_title = scene_title or date_title
    draw_cinematic_scene_header(draw, base_img, date_title, actual_title, archive_caption=caption_str, credit_str=credit_str, image_type=image_type, lang=lang)

    base_bg_png = os.path.join(temp_dir, "base_bg.png")
    base_img.convert("RGB").save(base_bg_png, "PNG")

    # 스타이즈본 방식 다이내믹 자막 엔진 연동 (VAD 무음 감지 + 호흡 가중치 + 키워드 골드 하이라이트)
    from src.subtitle_engine import (
        rule_based_chunking,
        get_audio_voice_activity,
        calculate_weighted_timings,
        render_highlighted_subtitle_png
    )

    if not dynamic_chunks:
        dynamic_chunks = rule_based_chunking(tts_text, lang=lang)

    lead_in = get_audio_voice_activity(audio_path, ffmpeg_bin=FFMPEG)
    timings = calculate_weighted_timings(dynamic_chunks, duration, lead_in=lead_in)

    sub_png_info = []
    for idx, (c_dict, st, en) in enumerate(timings):
        sub_p = os.path.join(temp_dir, f"sub_{idx:02d}.png")
        render_highlighted_subtitle_png(
            text=c_dict["text"],
            highlight_word=c_dict.get("highlight", ""),
            out_png=sub_p,
            font_path=FONT_PATH,
            highlight_color="#FFD700"
        )
        sub_png_info.append((sub_p, st, en))

    zoom_step = 0.08 / max(1, frames)
    vf = []
    if zoom_in:
        vf.append(f"scale=2332:4148,zoompan=z='min(1.0+{zoom_step:.7f}*on,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={CANVAS_W}x{CANVAS_H}:fps={FPS}")
    else:
        vf.append(f"scale=2332:4148,zoompan=z='max(1.08-{zoom_step:.7f}*on,1.0)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={CANVAS_W}x{CANVAS_H}:fps={FPS}")
    vf.append("format=yuv420p")

    for _, st, en in sub_png_info:
        vf.append(f"overlay=(W-w)/2:1390:enable='between(t,{st:.3f},{en:.3f})'")

    cmd = [
        FFMPEG, "-y", "-loglevel", "error",
        "-i", base_bg_png
    ]
    for sub_p, _, _ in sub_png_info:
        cmd += ["-i", sub_p]
    cmd += ["-i", audio_path]

    filter_complex = f"[0:v]{','.join(vf)}[v]"
    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", f"{1 + len(sub_png_info)}:a",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-shortest",
        out_chunk_mp4
    ]
    subprocess.run(cmd, check=True)


def render_cover_chunk(img, duration, out_mp4, zoom_in=True):
    frames = max(1, int(round(duration * FPS)))
    temp_cover_png = out_mp4 + "_temp.png"
    img.convert("RGB").save(temp_cover_png, "PNG")

    # 첫 28프레임(약 1.2초) 동안 정지(Hold)하여 시청자가 타이틀을 편안하게 읽을 수 있도록 한 후 부드러운 시네마틱 줌 전개
    hold_frames = min(frames // 3, 28)
    active_frames = max(1, frames - hold_frames)
    cover_step = 0.035 / active_frames
    if zoom_in:
        vf = f"scale=2332:4148,zoompan=z='if(lte(on,{hold_frames}),1.0,min(1.0+{cover_step:.7f}*(on-{hold_frames}),1.04))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={CANVAS_W}x{CANVAS_H}:fps={FPS},format=yuv420p"
    else:
        vf = f"scale=2332:4148,zoompan=z='if(lte(on,{hold_frames}),1.04,max(1.04-{cover_step:.7f}*(on-{hold_frames}),1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={CANVAS_W}x{CANVAS_H}:fps={FPS},format=yuv420p"

    cmd = [
        FFMPEG, "-y", "-loglevel", "error",
        "-loop", "1", "-i", temp_cover_png,
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-vf", vf,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        out_mp4
    ]
    subprocess.run(cmd, check=True)
    if os.path.exists(temp_cover_png):
        os.remove(temp_cover_png)


def assemble_final_shorts(chunk_mp4_list, bgm_mp3, final_output_mp4, temp_dir, bgm_vol=0.22):
    concat_txt = os.path.join(temp_dir, "concat.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for p in chunk_mp4_list:
            abs_p = os.path.abspath(p).replace(os.sep, '/')
            f.write(f"file '{abs_p}'\n")

    no_bgm_mp4 = os.path.join(temp_dir, "no_bgm_concat.mp4")
    subprocess.run([
        FFMPEG, "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", concat_txt,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        no_bgm_mp4
    ], check=True)

    p = subprocess.run([FFMPEG, "-i", no_bgm_mp4], stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", p.stderr)
    total_dur = 60.0
    if m:
        h, m_val, s = m.groups()
        total_dur = int(h) * 3600 + int(m_val) * 60 + float(s)

    filter_complex = (
        f"[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume={bgm_vol:.2f},atrim=0:{total_dur:.3f},afade=t=out:st={max(0.0, total_dur - 2.5):.3f}:d=2.5[bg];"
        f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[fg];"
        f"[fg][bg]amix=inputs=2:duration=first:normalize=0[a];"
        f"color=c=0xFFD700:s=1080x6:r={FPS}[goldbar];"
        f"[0:v][goldbar]overlay=x='-1080+1080*(t/{total_dur:.3f})':y=0[v]"
    )

    cmd = [
        FFMPEG, "-y", "-loglevel", "error",
        "-i", no_bgm_mp4,
        "-stream_loop", "-1", "-i", bgm_mp3,
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{total_dur:.3f}",
        final_output_mp4
    ]
    subprocess.run(cmd, check=True)
    return total_dur


def render_masterpiece_from_script(target_dir, lang=None):
    target_dir = os.path.abspath(target_dir)
    script_p = os.path.join(target_dir, "masterpiece_script.json")
    if not os.path.exists(script_p):
        raise FileNotFoundError(f"대본 파일을 찾을 수 없습니다: {script_p}")

    with open(script_p, "r", encoding="utf-8") as f:
        meta = json.load(f)

    if lang is None:
        lang = meta.get("lang")
        if not lang:
            if target_dir.endswith("en") or os.path.basename(target_dir) == "en":
                lang = "en"
            else:
                lang = "ko"

    corner_name = meta.get("corner_name", "History Time Machine" if lang == "en" else "1분 타임머신")
    event_title = meta.get("event_title", "On This Day" if lang == "en" else "역사 속 오늘")
    bgm_name = meta.get("bgm", "bgm_history_epic.mp3")

    images_dir = os.path.join(target_dir, "images")
    if not os.path.exists(images_dir) or not os.listdir(images_dir):
        parent_images = os.path.join(os.path.dirname(target_dir), "images")
        if os.path.exists(parent_images) and os.listdir(parent_images):
            images_dir = parent_images

    audio_dir = os.path.join(target_dir, "audio")
    temp_dir = os.path.join(target_dir, "master_render_temp")
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)

    date_basename = os.path.basename(os.path.normpath(target_dir))
    if date_basename in ("ko", "en"):
        date_basename = os.path.basename(os.path.dirname(os.path.normpath(target_dir)))

    match_year = re.search(r'\b(\d{3,4})년?\b', event_title)
    year_str = match_year.group(1) if match_year else date_basename[:4]

    digits = re.sub(r'\D', '', date_basename)
    mm, dd = 10, 24
    if len(digits) >= 8:
        mm = int(digits[4:6])
        dd = int(digits[6:8])

    month_names_en = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
                      "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"]
    m_name_en = month_names_en[max(0, min(11, mm - 1))]

    if lang == "en":
        master_date_title = f"{m_name_en} {dd}, {year_str} {event_title}".strip()
    else:
        master_date_title = f"{year_str}. {mm}. {dd} {event_title}".strip()

    print("==================================================================")
    print(f"🎬 [deepdive 정규 렌더링 - 언어: {lang.upper()}] [{corner_name}] {master_date_title}")
    print(f"   작업 디렉토리: {target_dir}")
    print(f"   사료 이미지 디렉토리: {images_dir}")
    print("==================================================================")

    chunks_list = []
    scenes = meta.get("scenes", [])

    # [Step 0] 0~4.2초 표지 인트로
    cover_bg = os.path.join(images_dir, "scene_1.jpg") if os.path.exists(os.path.join(images_dir, "scene_1.jpg")) else None
    main_yr = meta.get("main_year", year_str)
    
    if lang == "en":
        cover_header = f"{m_name_en} {dd} | HISTORY TIME MACHINE"
        kicker_txt = f"[ EVENTS OF {m_name_en} {dd}, {main_yr} ]" if len(digits) >= 8 else f"[ EVENTS OF {main_yr} ]"
        why_title = meta.get("why_today_title", "Why It Matters Today")
    else:
        try:
            dt = datetime.strptime(date_basename[:10], "%Y-%m-%d")
            weekday_kr = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"][dt.weekday()]
            date_str = f"{dt.year}년 {dt.month}월 {dt.day}일({weekday_kr})"
        except Exception:
            date_str = f"역사 속 오늘"
        cover_header = f"{date_str} | 역사 타임머신"
        kicker_txt = f"[ {main_yr}년 {mm}월 {dd}일의 사건 ]" if len(digits) >= 8 else f"[ {main_yr}년의 역사적 사건 ]"
        why_title = meta.get("why_today_title", "오늘 알아야 할 이유")

    cover_title = meta.get("hook_question", master_date_title)
    why_desc = meta.get("why_today_desc", "")

    COVER_DURATION = 4.2
    print(f"  [Step 0] 0~{COVER_DURATION}초 표지 인트로 영상 렌더링 (안정적 정지 홀드 적용)...")
    cover_img = render_intro_cover_image(cover_bg, cover_header, corner_name, cover_title, why_title, why_desc, target_date_str=date_basename, kicker_str=kicker_txt, lang=lang)
    cover_mp4 = os.path.join(temp_dir, "part_00_intro_cover.mp4")
    render_cover_chunk(cover_img, COVER_DURATION, cover_mp4, zoom_in=True)
    chunks_list.append(cover_mp4)

    # [Subtitle] 스타이즈본 벤치마킹 다이내믹 자막 청킹 & 키워드 분석
    from src.subtitle_engine import analyze_dynamic_chunks, build_pro_ass_file
    print(f"  [Subtitle] Gemini 2.5 Flash 기반 다이내믹 자막 청크 및 킬러 키워드 하이라이트 분석 중 (언어: {lang})...")
    analyzed_scenes = analyze_dynamic_chunks(scenes, lang=lang)
    analyzed_map = {s.get("scene_number", s.get("scene_no", idx+1)): s.get("chunks", []) for idx, s in enumerate(analyzed_scenes)}

    # ASS 자막 파일 생성
    try:
        ass_path = os.path.join(target_dir, "subtitles.ass")
        wav_paths = {sc.get("scene_number", idx+1): os.path.join(audio_dir, f"scene{sc.get('scene_number', idx+1)}.mp3") for idx, sc in enumerate(scenes)}
        durations = [get_audio_duration(wav_paths[sc.get("scene_number", idx+1)]) for idx, sc in enumerate(scenes)]
        build_pro_ass_file(scenes, analyzed_scenes, durations, ass_path, offset=COVER_DURATION, wav_paths=wav_paths)
        print(f"  [Subtitle] ASS 자막 파일 생성 완료: {ass_path}")
    except Exception as e:
        print(f"  [Subtitle] ASS 파일 빌드 경고 (계속 진행): {e}")

    # 본문 씬들
    for idx, sc in enumerate(scenes):
        s_num = sc.get("scene_number", idx + 1)
        script_text = sc.get("script", "")
        img_p = os.path.join(images_dir, f"scene_{s_num}.jpg")
        audio_p = os.path.join(audio_dir, f"scene{s_num}.mp3")
        dur = get_audio_duration(audio_p)
        image_type = sc.get("image_type", "archive")
        display_title = sc.get("display_title", "HISTORY MOMENT" if lang == "en" else "오늘의 역사")
        caption = sc.get("image_caption", "")
        credit = sc.get("credit", "Archive: Wikimedia Commons" if lang == "en" else "출처: 역사 기록 사료 / 위키미디어 커먼즈")

        # 씬별 상단 뱃지 텍스트
        if lang == "en":
            if s_num <= 4:
                sc_date_str = f"{m_name_en} {dd} | {main_yr}" if len(digits) >= 8 else f"{m_name_en} {dd}"
            else:
                sc_date_str = f"{m_name_en} {dd} | SPEED FACT"
        else:
            if s_num <= 4:
                sc_date_str = f"{mm}월 {dd}일 | {main_yr}년" if len(digits) >= 8 else f"{main_yr}년의 오늘"
            else:
                yr_m = re.search(r'\b(\d{3,4})년', script_text)
                sc_yr = yr_m.group(1) if yr_m else ""
                sc_date_str = f"{sc_yr}년의 오늘" if sc_yr else "오늘의 역사"

        print(f"  [Step {idx+1}] 씬 {s_num}: {dur:.1f}s - [{display_title}] {caption}...")
        sc_mp4 = os.path.join(temp_dir, f"part_{s_num:02d}.mp4")
        sc_tmp = os.path.join(temp_dir, f"tmp_{s_num}")
        dynamic_chunks = analyzed_map.get(s_num, [])
        render_body_scene_chunk(
            bg_path=img_p,
            corner_name=corner_name,
            date_title=sc_date_str,
            credit_str=credit,
            tts_text=script_text,
            audio_path=audio_p,
            duration=dur,
            out_chunk_mp4=sc_mp4,
            temp_dir=sc_tmp,
            zoom_in=(idx % 2 == 0),
            caption_str=caption,
            image_type=image_type,
            dynamic_chunks=dynamic_chunks,
            scene_title=display_title,
            lang=lang
        )
        chunks_list.append(sc_mp4)

    # [마지막 3.5초] 아웃트로 피날레
    print("  [Step 6] 3.5초 정갈한 인터랙션 아웃트로 피날레 렌더링...")
    last_img = os.path.join(images_dir, "scene_1.jpg") if os.path.exists(os.path.join(images_dir, "scene_1.jpg")) else (os.path.join(images_dir, f"scene_{len(scenes)}.jpg") if scenes else None)
    outro_debate = meta.get("outro_debate", {})
    if lang == "en":
        date_title_h = f"{m_name_en} {dd} History Documentary"
    else:
        date_title_h = f"{mm}월 {dd}일의 역사 다큐멘터리" if len(digits) >= 8 else "역사 다큐멘터리"
    outro_img = render_outro_finale_image(last_img, "Public History Archive" if lang == "en" else "오늘의 역사 아카이브", outro_debate=outro_debate, date_title_str=date_title_h, lang=lang)
    outro_mp4 = os.path.join(temp_dir, "part_99_outro_finale.mp4")
    render_cover_chunk(outro_img, 3.5, outro_mp4, zoom_in=False)
    chunks_list.append(outro_mp4)

    # Concat + BGM 오토덕킹 + 상단 6px 골드 진행선 바
    print("  [Step 7] Concat + BGM 오토덕킹 + 상단 6px 골드 진행선 바 합성...")
    bgm_path = os.path.join(BGM_DIR, bgm_name)
    if not os.path.exists(bgm_path):
        bgm_path = os.path.join(BGM_DIR, "bgm_history_epic.mp3")

    final_output = os.path.join(target_dir, f"final_shorts_{lang}.mp4")
    total_sec = assemble_final_shorts(chunks_list, bgm_path, final_output, temp_dir, bgm_vol=0.22)
    file_size_mb = os.path.getsize(final_output) / (1024 * 1024)

    # 하위 호환성을 위해 기존 이름 파일도 생성/복사
    compat_output = os.path.join(target_dir, f"final_masterpiece_{date_basename}.mp4")
    try:
        shutil.copy2(final_output, compat_output)
    except Exception:
        pass

    print(f"\n🎉 [마스터피스 완성 ({lang.upper()})] {final_output}")
    print(f"  총 재생시간: {total_sec:.2f}초 | 파일 크기: {file_size_mb:.2f} MB")
    return final_output

if __name__ == "__main__":
    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        target_path = sys.argv[1]
    else:
        sys.path.insert(0, BASE_DIR)
        from src.config import get_daily_dir
        target_date = sys.argv[1] if len(sys.argv) > 1 else None
        target_path = get_daily_dir(target_date)
    render_masterpiece_from_script(target_path)
