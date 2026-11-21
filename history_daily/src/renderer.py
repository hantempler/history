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
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
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
FPS = 30
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

    f_brand = get_font(34)
    f_main = get_font(68)
    gold_color = (255, 215, 0)
    brand_color = (0, 210, 255)  # 시네마틱 스카이블루/네온 시안 (#00D2FF)

    # 1. 상단 브랜딩 ("● 역사 딥다이브 | 11.17" 시네마틱 스카이블루/네온 시안으로 배치)
    brand_y = 120
    draw.ellipse([70, brand_y - 10, 88, brand_y + 8], fill=brand_color)

    digits = re.sub(r'\D', '', target_date_str or "")
    if len(digits) >= 8:
        mm = int(digits[4:6])
        dd = int(digits[6:8])
        date_label = f"{mm:02d}.{dd:02d}"
    else:
        date_label = "11.17"

    brand_label = highlight_cat or ("HISTORY TIME MACHINE" if lang == "en" else "역사 딥다이브")
    brand_text = f"{brand_label}   |   {date_label}"
    draw.text((105, brand_y), brand_text, fill=brand_color, font=f_brand, anchor="lm")

    # 2. 메인 질문 제목 (다른 사족 없이 제목만 단독 배치, 모두 노란색으로 동일하게 표시)
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

    start_y = 540 if len(lines) <= 2 else 480
    step_y = 104
    for idx_l, l_str in enumerate(lines[:3]):
        b = draw.textbbox((0, 0), l_str, font=f_main)
        lx = (CANVAS_W - (b[2] - b[0])) // 2
        ly = start_y + idx_l * step_y
        # 3.5px 드롭 섀도우
        draw.text((lx + 3, ly + 3), l_str, font=f_main, fill=(0, 0, 0, 240))
        # 모두 노란색(#FFD700) 통일 렌더링 + 4.0px 블랙 아웃라인
        draw.text((lx, ly), l_str, font=f_main, fill=gold_color, stroke_width=4, stroke_fill="black")

    # 사족(골드 분리선, 오늘 알아야 할 이유, 깊이보기) 전면 삭제 완료
    return base_img


# -------------------------------------------------------------
# [본문용] 상단 소제목 독립 오버레이 (번호/사료 제외 순수 소제목만 노란색 단독 렌더링)
# -------------------------------------------------------------
def render_scene_header_overlay_png(scene_idx, scene_title, archive_caption=None, credit_str=None, image_type="archive", lang="ko", out_png=None):
    from src.subtitle_engine import format_sub_display
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. 탑 소제목 라벨 (번호 01 및 사료 제외, 순수 소제목만 56pt 볼드 노란색 단독 표시)
    font_chapter = get_font(56)
    clean_title = format_sub_display(sanitize_tofu((scene_title or "").strip()))
    gold_color = (255, 215, 0)

    cb = draw.textbbox((0, 0), clean_title, font=font_chapter)
    cw = cb[2] - cb[0]
    cx = (CANVAS_W - cw) // 2
    cy = 210  # MarginV=230 equivalent from top

    # 3.5px 블랙 드롭 섀도우
    draw.text((cx + 3, cy + 3), clean_title, font=font_chapter, fill=(0, 0, 0, 220), stroke_width=5, stroke_fill=(0, 0, 0, 220))
    # 6.0px 블랙 아웃라인 & 전체 노란색(#FFD700) 통일 렌더링
    draw.text((cx, cy), clean_title, font=font_chapter, fill=gold_color, stroke_width=6, stroke_fill="black")

    # 2. 크레딧 정보 (최하단 y=1885 은은한 워터마크)
    if credit_str:
        f_cred = get_font(18)
        cr_b = draw.textbbox((0, 0), credit_str, font=f_cred)
        draw.text(((CANVAS_W - (cr_b[2] - cr_b[0])) // 2, 1885), credit_str, font=f_cred, fill=(180, 195, 215, 140))

    if out_png:
        img.save(out_png, "PNG")
    return img


# -------------------------------------------------------------
# [전체 씬용] 상단 브랜드 워터마크 오버레이 (Y=120 "● 역사 딥다이브 | 11.17" 전체 노란색 통일)
# -------------------------------------------------------------
def generate_brand_overlay_png(corner_name, target_date_str, topic_title=None, out_png=None, lang="ko"):
    from src.subtitle_engine import format_sub_display
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    brand_y = 120
    brand_color = (0, 210, 255)  # 시네마틱 스카이블루/네온 시안 (#00D2FF)

    # 1. 네온 시안 인디케이터 도트
    draw.ellipse([70, brand_y - 10, 88, brand_y + 8], fill=brand_color)

    # 2. 날짜 및 브랜딩 텍스트 (시안/스카이블루로 표시)
    digits = re.sub(r'\D', '', target_date_str or "")
    if len(digits) >= 8:
        mm = int(digits[4:6])
        dd = int(digits[6:8])
        date_label = f"{mm:02d}.{dd:02d}"
    else:
        date_label = "11.17"

    brand_label = corner_name or ("HISTORY TIME MACHINE" if lang == "en" else "역사 딥다이브")
    font_brand = get_font(34)
    # 뒤에 토픽명 없이 "● 역사 딥다이브 | 11.17"만 시안/스카이블루로 표시
    brand_text = f"{brand_label}   |   {date_label}"
    draw.text((105, brand_y), brand_text, fill=brand_color, font=font_brand, anchor="lm")

    if out_png:
        img.save(out_png, "PNG")
    return img


# -------------------------------------------------------------
def draw_cinematic_scene_header(draw, base_img, date_str, scene_title, archive_caption=None, credit_str=None, image_type="archive", lang="ko"):
    # 하위 호환용 스텁
    return 280


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
# 본문 씬 렌더러 (Starisborn 규격 74pt 다이내믹 자막 + 정적 탑 챕터 + 6대 시네마틱 모션)
# -------------------------------------------------------------
def render_body_scene_chunk(bg_path, corner_name, date_title, credit_str, tts_text, audio_path, duration, out_chunk_mp4, temp_dir, camera_motion="push_in", sfx_path=None, subtitle_cards=None, caption_str=None, image_type="archive", dynamic_chunks=None, scene_title=None, lang="ko", highlight_keywords=None):
    os.makedirs(temp_dir, exist_ok=True)
    frames = max(1, int(round(duration * FPS)))

    # 1. 배경 이미지 (텍스트 없이 순수 이미지 로드 + 상하단 시네마틱 비네팅)
    base_img = load_and_fill_fullscreen(bg_path)
    base_img = apply_top_soft_gradient(base_img)

    # 하단 자막 영역 소프트 다크 스크림 그라데이션 (가독성 100% 보장)
    scrim = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(scrim)
    for sy in range(1200, CANVAS_H):
        alpha = int(120 * ((sy - 1200) / (CANVAS_H - 1200)) ** 1.2)
        s_draw.line([(0, sy), (CANVAS_W, sy)], fill=(0, 0, 0, alpha))
    base_img = Image.alpha_composite(base_img, scrim)

    base_bg_png = os.path.join(temp_dir, "base_bg.png")
    base_img.convert("RGB").save(base_bg_png, "PNG")

    # 2. 상단 탑 챕터 및 사료 캡션 독립 오버레이 (Starisborn TopChapter 규격, 줌팬과 분리)
    m_s = re.search(r'scene(\d+)', os.path.basename(audio_path))
    s_idx_num = int(m_s.group(1)) if m_s else 1
    header_png = os.path.join(temp_dir, f"header_{s_idx_num:02d}.png")
    render_scene_header_overlay_png(
        scene_idx=s_idx_num,
        scene_title=scene_title or date_title,
        archive_caption=caption_str,
        credit_str=credit_str,
        image_type=image_type,
        lang=lang,
        out_png=header_png
    )

    # 3. Google Cloud TTS SSML 실측 타임스탬프 우선 적용 (오차 0%)
    timings = []
    if dynamic_chunks and len(dynamic_chunks) > 0 and "start" in dynamic_chunks[0]:
        timings = [(c, float(c["start"]), float(c["end"])) for c in dynamic_chunks]
    else:
        s_idx_str = str(s_idx_num)
        cand_tps = [
            os.path.join(os.path.dirname(audio_path), f"timepoints_scene{s_idx_str}.json"),
            os.path.join(os.path.dirname(os.path.dirname(audio_path)), f"timepoints_scene{s_idx_str}.json")
        ]
        for tp_f in cand_tps:
            if os.path.exists(tp_f):
                try:
                    with open(tp_f, "r", encoding="utf-8") as f_tp:
                        tp_d = json.load(f_tp)
                        timings = [(c, float(c["start"]), float(c["end"])) for c in tp_d.get("chunks", [])]
                        print(f"    ⏱️ [Scene {s_idx_str}] 구글 TTS 실측 Timepoints 적용 완료 ({len(timings)}개 청크)")
                        break
                except Exception:
                    pass

    # 실측 파일이 없는 경우 안전 폴백 (기존 가중 배분)
    if not timings:
        from src.subtitle_engine import rule_based_chunking, get_audio_voice_activity, calculate_weighted_timings
        if not dynamic_chunks:
            dynamic_chunks = rule_based_chunking(tts_text, lang=lang)
        lead_in = get_audio_voice_activity(audio_path, ffmpeg_bin=FFMPEG)
        timings = calculate_weighted_timings(dynamic_chunks, duration, lead_in=lead_in)

    # 4. Starisborn 74pt 다이내믹 자막 카드 렌더링 (다크 박스 없음, 순수 타이포그래피)
    from src.subtitle_engine import render_highlighted_subtitle_png
    sub_png_info = []
    for idx, (c_dict, st, en) in enumerate(timings):
        sub_p = os.path.join(temp_dir, f"sub_{idx:02d}.png")
        render_highlighted_subtitle_png(
            text=c_dict["text"],
            highlight_word=c_dict.get("highlight", ""),
            out_png=sub_p,
            font_path=FONT_PATH,
            highlight_color="#FFE600",
            highlight_keywords=highlight_keywords
        )
        sub_png_info.append((sub_p, st, en))

    # 5. 6대 시네마틱 카메라 모션 수식 (스타이즈본 1% 규격 이식)
    vignette_prefix = ""
    total_frames = max(1, frames)

    if camera_motion == "face_zoom":
        step = 0.15 / total_frames
        zoom_expr = f"min(1.05+on*{step:.7f}, 1.20)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih*0.35-(ih/zoom*0.35)"
    elif camera_motion == "push_in":
        step = 0.19 / total_frames
        zoom_expr = f"min(1.05+on*{step:.7f}, 1.24)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif camera_motion == "pan_lr":
        zoom_expr = "1.18"
        x_expr = f"(iw-iw/zoom)*(on/{max(1, total_frames - 1)})"
        y_expr = "ih/2-(ih/zoom/2)"
    elif camera_motion == "tilt_up":
        zoom_expr = "1.18"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = f"(ih-ih/zoom)*(0.75-0.55*(on/{max(1, total_frames - 1)}))"
    elif camera_motion == "vignette_zoom_out":
        vignette_prefix = "vignette=PI/4.2,"
        step = 0.20 / total_frames
        zoom_expr = f"max(1.20-on*{step:.7f}, 1.00)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif camera_motion == "slow_drift":
        zoom_expr = "1.15"
        x_expr = f"(iw-iw/zoom)*(0.15+0.7*(on/{max(1, total_frames - 1)}))"
        y_expr = f"(ih-ih/zoom)*(0.2+0.6*(on/{max(1, total_frames - 1)}))"
    else:
        step = 0.08 / total_frames
        zoom_expr = f"min(1.0+{step:.7f}*on, 1.08)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    # 필터 체인 구성:
    # 0:v -> 켄번스 모션 -> [bg_v]
    # [bg_v][1:v]overlay=0:0 -> 상단 탑 챕터 헤더 오버레이 -> [v0]
    # [v0] 위에 74pt 다이내믹 자막 오버레이 순차 결합 (모바일 세이프존 y=1410)
    filter_parts = []
    filter_parts.append(f"[0:v]{vignette_prefix}scale=2332:4148,zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':d={frames}:s={CANVAS_W}x{CANVAS_H}:fps={FPS},format=yuv420p[bg_v]")
    filter_parts.append(f"[bg_v][1:v]overlay=0:0[v0]")

    last_v = "v0"
    for s_i, (_, st, en) in enumerate(sub_png_info):
        sub_inp_idx = 2 + s_i
        next_v = f"v{s_i+1}"
        filter_parts.append(f"[{last_v}][{sub_inp_idx}:v]overlay=(W-w)/2:1410:enable='between(t,{st:.3f},{en:.3f})'[{next_v}]")
        last_v = next_v

    cmd = [
        FFMPEG, "-y", "-loglevel", "error",
        "-i", base_bg_png,
        "-i", header_png
    ]
    for sub_p, _, _ in sub_png_info:
        cmd += ["-i", sub_p]
    cmd += ["-i", audio_path]

    nar_idx = 2 + len(sub_png_info)

    if sfx_path and os.path.exists(sfx_path):
        cmd += ["-i", sfx_path]
        sfx_idx = nar_idx + 1
        filter_parts.append(f"[{nar_idx}:a]volume=1.0[nar];[{sfx_idx}:a]volume=0.20[whoosh];[nar][whoosh]amix=inputs=2:duration=first:normalize=0[a]")
        final_map_a = "[a]"
    else:
        filter_parts.append(f"[{nar_idx}:a]volume=1.0[a]")
        final_map_a = "[a]"

    filter_complex = ";".join(filter_parts)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", f"[{last_v}]", "-map", final_map_a,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-shortest",
        out_chunk_mp4
    ]
    subprocess.run(cmd, check=True)


def render_cover_chunk(img, duration, out_mp4, zoom_in=True, sfx_impact_path=None):
    frames = max(1, int(round(duration * FPS)))
    temp_cover_png = out_mp4 + "_temp.png"
    img.convert("RGB").save(temp_cover_png, "PNG")

    hold_frames = min(frames // 3, 28)
    active_frames = max(1, frames - hold_frames)
    cover_step = 0.035 / active_frames
    if zoom_in:
        vf = f"scale=2332:4148,zoompan=z='if(lte(on,{hold_frames}),1.0,min(1.0+{cover_step:.7f}*(on-{hold_frames}),1.04))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={CANVAS_W}x{CANVAS_H}:fps={FPS},format=yuv420p"
    else:
        vf = f"scale=2332:4148,zoompan=z='if(lte(on,{hold_frames}),1.04,max(1.04-{cover_step:.7f}*(on-{hold_frames}),1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={CANVAS_W}x{CANVAS_H}:fps={FPS},format=yuv420p"

    if sfx_impact_path and os.path.exists(sfx_impact_path):
        filter_complex = f"[0:v]{vf}[v];[1:a]volume=0.40,atrim=0:0.8,apad=whole_dur={duration:.3f}[a]"
        cmd = [
            FFMPEG, "-y", "-loglevel", "error",
            "-loop", "1", "-i", temp_cover_png,
            "-i", sfx_impact_path,
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
            "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            out_mp4
        ]
    else:
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


def assemble_final_shorts(chunk_mp4_list, bgm_mp3, final_output_mp4, temp_dir, bgm_vol=0.12, brand_overlay_png=None, thumb_duration=3.5):
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

    # 사이드체인 오디오 덕킹: 성우 발화 시 BGM 볼륨 -18dB 자동 감쇄, 쉼표 구간 즉시 복원
    filter_complex = (
        f"[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume={bgm_vol:.2f},atrim=0:{total_dur:.3f},afade=t=out:st={max(0.0, total_dur - 2.5):.3f}:d=2.5[bg];"
        f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,asplit=2[fg1][fg2];"
        f"[bg][fg2]sidechaincompress=threshold=0.06:ratio=6:attack=40:release=350[ducked_bg];"
        f"[fg1][ducked_bg]amix=inputs=2:duration=first:normalize=0[a];"
        f"color=c=0xFFD700:s=1080x6:r={FPS}[goldbar];"
    )

    cmd = [
        FFMPEG, "-y", "-loglevel", "error",
        "-i", no_bgm_mp4,
        "-stream_loop", "-1", "-i", bgm_mp3
    ]

    # 상단 브랜드 워터마크 오버레이 (Starisborn 1:1 규격: 썸네일 이후 t >= thumb_duration 전 구간 유지)
    if brand_overlay_png and os.path.exists(brand_overlay_png):
        cmd += ["-i", brand_overlay_png]
        filter_complex += (
            f"[0:v][goldbar]overlay=x='-1080+1080*(t/{total_dur:.3f})':y=0[v_gold];"
            f"[v_gold][2:v]overlay=0:0:enable='gte(t,{thumb_duration:.3f})'[v]"
        )
    else:
        filter_complex += f"[0:v][goldbar]overlay=x='-1080+1080*(t/{total_dur:.3f})':y=0[v]"

    cmd += [
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
    if not os.path.exists(audio_dir) or not os.listdir(audio_dir):
        ko_audio = os.path.join(target_dir, "ko", "audio")
        parent_audio = os.path.join(os.path.dirname(target_dir), "audio")
        if os.path.exists(ko_audio) and os.listdir(ko_audio):
            audio_dir = ko_audio
        elif os.path.exists(parent_audio) and os.listdir(parent_audio):
            audio_dir = parent_audio
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

    # [SFX] 로열티 프리 효과음 라이브러리 탑재
    from src.sfx_manager import ensure_sfx_assets
    sfx_dict = ensure_sfx_assets()

    # [Step 0] 0~3.5초 표지 인트로 (0초 서브베이스 Impact SFX 탑재)
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

    COVER_DURATION = 3.5
    print(f"  [Step 0] 0~{COVER_DURATION}초 표지 인트로 영상 렌더링 (0초 Impact SFX + 안정적 정지 홀드 적용)...")
    cover_img = render_intro_cover_image(cover_bg, cover_header, corner_name, cover_title, why_title, why_desc, target_date_str=date_basename, kicker_str=kicker_txt, lang=lang)
    cover_mp4 = os.path.join(temp_dir, "part_00_intro_cover.mp4")
    render_cover_chunk(cover_img, COVER_DURATION, cover_mp4, zoom_in=True, sfx_impact_path=sfx_dict.get("impact"))
    chunks_list.append(cover_mp4)

    # [Brand] Starisborn 규격 상단 브랜드 워터마크 오버레이 생성 (Y=120 골드 닷 + 브랜딩 + 토픽)
    brand_overlay_png = os.path.join(temp_dir, "brand_overlay.png")
    generate_brand_overlay_png(
        corner_name=corner_name,
        target_date_str=date_basename,
        topic_title=meta.get("title") or event_title,
        out_png=brand_overlay_png,
        lang=lang
    )

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
        c_motion = sc.get("camera_motion", "push_in")

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

        print(f"  [Step {idx+1}] 씬 {s_num}: {dur:.1f}s [{c_motion}] - [{display_title}] {caption}...")
        sc_mp4 = os.path.join(temp_dir, f"part_{s_num:02d}.mp4")
        sc_tmp = os.path.join(temp_dir, f"tmp_{s_num}")
        dynamic_chunks = sc.get("chunks") or analyzed_map.get(s_num, [])
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
            camera_motion=c_motion,
            sfx_path=sfx_dict.get("whoosh"),
            caption_str=caption,
            image_type=image_type,
            dynamic_chunks=dynamic_chunks,
            scene_title=display_title,
            lang=lang,
            highlight_keywords=sc.get("highlight_keywords", [])
        )
        chunks_list.append(sc_mp4)

    # Concat + BGM 오토덕킹 + 상단 6px 골드 진행선 바 + 상단 브랜드 워터마크
    print("  [Step 7] Concat + BGM 사이드체인 오디오 덕킹 + 상단 6px 골드 진행선 바 + 브랜드 오버레이 합성...")
    bgm_path = os.path.join(BGM_DIR, bgm_name)
    if not os.path.exists(bgm_path):
        bgm_path = os.path.join(BGM_DIR, "bgm_history_epic.mp3")

    final_output = os.path.join(target_dir, f"final_shorts_{lang}.mp4")
    total_sec = assemble_final_shorts(
        chunks_list, bgm_path, final_output, temp_dir,
        bgm_vol=0.12,
        brand_overlay_png=brand_overlay_png,
        thumb_duration=COVER_DURATION
    )
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
        edition = sys.argv[2] if len(sys.argv) > 2 else "history"
        ko_cand = get_daily_dir(target_date, edition=edition)
        if os.path.exists(os.path.join(ko_cand, "masterpiece_script.json")):
            target_path = ko_cand
        else:
            target_path = get_daily_dir(target_date)
    render_masterpiece_from_script(target_path)
