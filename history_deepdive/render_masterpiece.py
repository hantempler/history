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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, 'config')
CRED_PATH = os.path.join(CONFIG_DIR, 'application_default_credentials.json')
if os.path.exists(CRED_PATH):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CRED_PATH

FONT_PATH = os.path.join(CONFIG_DIR, 'GmarketSansTTFBold.ttf')
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
    "시국 평행이론": (149, 165, 166)   # 네오 실버
}

def get_audio_duration(path: str) -> float:
    cmd = [FFMPEG, "-i", path]
    p = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", p.stderr)
    if m:
        h, m_val, s = m.groups()
        return int(h)*3600 + int(m_val)*60 + float(s)
    return 5.0

# -------------------------------------------------------------
# 1. 1080x1920 풀스크린 배경 로드
# -------------------------------------------------------------
def load_and_fill_fullscreen(img_path):
    if not img_path or not os.path.exists(img_path):
        fallback_dirs = [
            os.path.join(BASE_DIR, 'assets'),
            r"g:\내 드라이브\2_프로젝트\PRJ_history\history_shorts_v0\assets"
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
        if y < 460:
            pix[0, y] = int(185 * (1.0 - y / 460.0))
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
        if ratio < 0.35:
            pix[0, y] = int(185 * (1 - ratio / 0.35))
        elif ratio > 0.60:
            pix[0, y] = int(210 * ((ratio - 0.60) / 0.40))
        else:
            pix[0, y] = 0
    grad = grad.resize((w, h))
    shade = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shade.putalpha(grad)
    return Image.alpha_composite(img, shade)

WEEKDAY_CORNERS_MATRIX = [
    ["역사 딥다이브", "미스터리 파일", "실록 오늘", "전술·전쟁사"],  # 1행: 월·화·수·목
    ["인물 60초", "역사 VS", "시국 평행이론"]                    # 2행: 금·토·일
]

# -------------------------------------------------------------
# 2. [0~3초] PRJ_1min_knowledge 표지 인트로 생성 (시안 A: 고대비 글래스 알약)
# -------------------------------------------------------------
def render_intro_cover_image(bg_path, header_str, highlight_cat, main_title, why_title=None, why_desc=None):
    base_img = load_and_fill_fullscreen(bg_path)
    base_img = apply_intro_gradient(base_img)
    draw = ImageDraw.Draw(base_img)

    font_header = ImageFont.truetype(FONT_PATH, 36)
    font_badge = ImageFont.truetype(FONT_PATH, 26)
    font_badge_bold = ImageFont.truetype(FONT_PATH, 27)
    font_title = ImageFont.truetype(FONT_PATH, 66)

    # 1. 상단 날짜 및 헤더 (쇼츠 플레이어 컨트롤러 회피 Y=180 안전구역)
    h_bb = draw.textbbox((0, 0), header_str, font=font_header)
    draw.text((int((CANVAS_W - (h_bb[2]-h_bb[0])) // 2), 180), header_str, font=font_header, fill=(255, 255, 255, 255), stroke_width=3, stroke_fill='black')

    # 2. 요일별 7대 코너 2줄 캡슐 매트릭스 (시안 A: 236/250x54 고대비 글래스 알약)
    pill_w_r1 = 236
    pill_w_r2 = 250
    pill_h = 54
    gap_x = 16
    gap_y = 14
    start_y = 245

    for r_idx, row in enumerate(WEEKDAY_CORNERS_MATRIX):
        pw = pill_w_r1 if r_idx == 0 else pill_w_r2
        row_w = len(row) * pw + (len(row) - 1) * gap_x
        row_start_x = (CANVAS_W - row_w) / 2
        curr_y = start_y + r_idx * (pill_h + gap_y)

        for c_idx, corner in enumerate(row):
            curr_x = row_start_x + c_idx * (pw + gap_x)
            box = [int(curr_x), int(curr_y), int(curr_x + pw), int(curr_y + pill_h)]
            is_match = (corner == highlight_cat) or (highlight_cat in corner) or (corner in highlight_cat)
            if is_match:
                # 활성 코너 (오늘자 편성): 골드(#FFD400) + 순백 외곽선 + 볼드 블랙 텍스트
                draw.rounded_rectangle(box, radius=pill_h//2, fill=(255, 212, 0, 255), outline=(255, 255, 255, 255), width=2)
                t_bb = draw.textbbox((0, 0), corner, font=font_badge_bold)
                tx = curr_x + (pw - (t_bb[2]-t_bb[0]))/2
                ty = curr_y + (pill_h - (t_bb[3]-t_bb[1]))/2 - 2
                draw.text((int(tx), int(ty)), corner, font=font_badge_bold, fill=(12, 16, 24))
            else:
                # 비활성 코너: 딥슬레이트 차콜(94% 불투명) + 화이트 외곽선(170) + 또렷한 화이트 텍스트
                draw.rounded_rectangle(box, radius=pill_h//2, fill=(15, 22, 35, 240), outline=(255, 255, 255, 170), width=2)
                t_bb = draw.textbbox((0, 0), corner, font=font_badge)
                tx = curr_x + (pw - (t_bb[2]-t_bb[0]))/2
                ty = curr_y + (pill_h - (t_bb[3]-t_bb[1]))/2 - 2
                draw.text((int(tx), int(ty)), corner, font=font_badge, fill=(255, 255, 255), stroke_width=1, stroke_fill=(0, 0, 0, 160))

    # 3. 중앙 대형 메인 타이틀 (골든 존 배치)
    clean_title = main_title.strip()
    if len(clean_title) > 16 and "\n" not in clean_title:
        mid = len(clean_title) // 2
        sp = clean_title.rfind(" ", 0, mid + 5)
        if sp != -1:
            clean_title = clean_title[:sp] + "\n" + clean_title[sp+1:]

    lines = clean_title.split("\n")
    title_box = draw.multiline_textbbox((0, 0), clean_title, font=font_title, spacing=18)
    tw = title_box[2] - title_box[0]
    th = title_box[3] - title_box[1]
    title_y = 620 if len(lines) > 1 else 650
    draw.multiline_text((int((CANVAS_W - tw) // 2), int(title_y)), clean_title, font=font_title, fill='#FFD700', align='center', spacing=18, stroke_width=5, stroke_fill='black')

    return base_img

# -------------------------------------------------------------
# 3. [본문용] 상단 스마트 브랜딩 헤더 (날짜 + 제목 2줄 분리 배치)
# -------------------------------------------------------------
def draw_body_minimal_header(draw, corner_name, event_date_title):
    corner_bg = CORNER_COLOR_MAP.get(corner_name, (229, 169, 60))
    font_badge = ImageFont.truetype(FONT_PATH, 28)
    font_date = ImageFont.truetype(FONT_PATH, 30)
    font_title = ImageFont.truetype(FONT_PATH, 38)

    # 1. 코너 알약 배지: 상단 노치 안전영역 (Y=180, 중앙 정렬)
    cb_bbox = draw.textbbox((0, 0), corner_name, font=font_badge)
    cb_w = cb_bbox[2] - cb_bbox[0]
    cb_h = cb_bbox[3] - cb_bbox[1]

    pill_w = cb_w + 34
    pill_h = 44
    pill_x = (CANVAS_W - pill_w) / 2
    pill_y = 180

    draw.rounded_rectangle([int(pill_x), int(pill_y), int(pill_x + pill_w), int(pill_y + pill_h)], radius=pill_h // 2, fill=(*corner_bg, 245))
    text_col = (18, 22, 32) if (corner_bg[0]*0.299 + corner_bg[1]*0.587 + corner_bg[2]*0.114) > 130 else (255, 255, 255)
    tx = pill_x + (pill_w - cb_w) / 2
    ty = pill_y + (pill_h - cb_h) / 2 - 2
    draw.text((int(tx), int(ty)), corner_name, font=font_badge, fill=text_col)

    # 2. 사건 일자와 사건 제목을 2줄로 스마트 분리
    date_match = re.match(r"^(\d{4}[\.\s\-년]+(?:\d{1,2}[\.\s\-월]+)?(?:\d{1,2}[\.\s\-일]*)?\.?)(.*)$", event_date_title.strip())
    if date_match and date_match.group(2).strip():
        date_part = date_match.group(1).strip()
        title_part = date_match.group(2).strip()
    else:
        parts = event_date_title.strip().split(" ", 3)
        if len(parts) >= 4 and any(c.isdigit() for c in parts[0]):
            date_part = " ".join(parts[:3])
            title_part = parts[3]
        else:
            date_part = ""
            title_part = event_date_title.strip()

    # 날짜 렌더링 (1행: Y=240, 샴페인 골드, 30pt)
    current_y = 240
    if date_part:
        dt_bb = draw.textbbox((0, 0), date_part, font=font_date)
        dt_w = dt_bb[2] - dt_bb[0]
        draw.text((int((CANVAS_W - dt_w) // 2), int(current_y)), date_part, font=font_date, fill=(255, 232, 163), stroke_width=3, stroke_fill='black')
        current_y += 45

    # 제목 렌더링: 820px 이내로 단어 단위 줄바꿈 (2~3행: 38pt 화이트, Y=285)
    words = title_part.strip().split()
    wrapped_title = []
    cur_line = []
    for w in words:
        test_line = " ".join(cur_line + [w])
        bb = draw.textbbox((0, 0), test_line, font=font_title)
        if (bb[2] - bb[0]) > 820 and cur_line:
            wrapped_title.append(" ".join(cur_line))
            cur_line = [w]
        else:
            cur_line.append(w)
    if cur_line:
        wrapped_title.append(" ".join(cur_line))
    clean_title = "\n".join(wrapped_title)

    t_box = draw.multiline_textbbox((0, 0), clean_title, font=font_title, spacing=10)
    tw = t_box[2] - t_box[0]
    th = t_box[3] - t_box[1]
    draw.multiline_text((int((CANVAS_W - tw) // 2), int(current_y)), clean_title, font=font_title, fill=(255, 255, 255, 250), align='center', spacing=10, stroke_width=3, stroke_fill='black')

    return current_y + th

# -------------------------------------------------------------
# 3. 자막 청크 분할 (외톨이 단어 원천 차단)
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
                chunks.append(s_lines[i] + "\n" + s_lines[i+1])
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
# 4. 자막 가독성 카드 (820px 안전 너비 + 다크 라운드 플레이트)
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

# -------------------------------------------------------------
# 5. 이미지 출처 및 고증 라벨 (상단 제목 직하단 또는 아웃트로 하단)
# -------------------------------------------------------------
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
            draw.text((int(cx), int(cur_y)), cap_full, font=font_cap, fill=(255, 235, 175), stroke_width=2, stroke_fill='black')
            cur_y += 35

        if credit_str:
            font_credit = ImageFont.truetype(FONT_PATH, 21)
            cb = draw.textbbox((0, 0), credit_str, font=font_credit)
            cw = cb[2] - cb[0]
            cx = (CANVAS_W - cw) // 2 if center else 55
            draw.text((int(cx), int(cur_y)), credit_str, font=font_credit, fill=(215, 225, 238), stroke_width=2, stroke_fill='black')
    else:
        x = 55
        if caption_str:
            font_cap = ImageFont.truetype(FONT_PATH, 25)
            prefix = "사료: " if image_type == "archive" else "고증 복원: "
            cap_full = f"{prefix}{caption_str}"
            draw.text((x, 1632), cap_full, font=font_cap, fill=(255, 232, 163), stroke_width=3, stroke_fill='black')
        if credit_str:
            font_credit = ImageFont.truetype(FONT_PATH, 21)
            y = 1675 if caption_str else 1680
            draw.text((x, y), credit_str, font=font_credit, fill=(210, 218, 230), stroke_width=2, stroke_fill='black')

# -------------------------------------------------------------
# 6. 아웃트로 3단 피날레 이미지 (3.0s)
# -------------------------------------------------------------
def render_outro_finale_image(bg_path, credit_str, why_title=None, why_desc=None):
    base_img = load_and_fill_fullscreen(bg_path)
    base_img = apply_intro_gradient(base_img)
    draw = ImageDraw.Draw(base_img)

    font_sub_top = ImageFont.truetype(FONT_PATH, 38)
    font_cta_main = ImageFont.truetype(FONT_PATH, 82)
    font_sub_bottom = ImageFont.truetype(FONT_PATH, 32)

    if why_title and why_desc:
        # 1. 상단: '오늘 알아야 할 이유' 소제목 + [안 1] 앤틱 샴페인 골드 명언 인용 스타일
        font_why_t = ImageFont.truetype(FONT_PATH, 34)
        font_why_d = ImageFont.truetype(FONT_PATH, 38)

        # 소제목: 세련된 시안 블루 (Y=565)
        wb = draw.textbbox((0, 0), why_title, font=font_why_t)
        draw.text((int((CANVAS_W - (wb[2]-wb[0])) // 2), 565), why_title, font=font_why_t, fill='#38BDF8', stroke_width=2, stroke_fill='black')

        # 교훈 본문: 앤틱 샴페인 골드 (#FFE082) + 큰따옴표 “ ... ” (Y=635)
        words = why_desc.strip().replace('\n', ' ').split()
        wrapped_desc = []
        cur_line = []
        for w in words:
            test_line = " ".join(cur_line + [w])
            bb = draw.textbbox((0, 0), test_line, font=font_why_d)
            if (bb[2] - bb[0]) > 840 and cur_line:
                wrapped_desc.append(" ".join(cur_line))
                cur_line = [w]
            else:
                cur_line.append(w)
        if cur_line:
            wrapped_desc.append(" ".join(cur_line))
        clean_desc = "\n".join(wrapped_desc)
        quote_desc = f"“{clean_desc}”"

        db = draw.multiline_textbbox((0, 0), quote_desc, font=font_why_d, spacing=16)
        dw = db[2] - db[0]
        draw.multiline_text((int((CANVAS_W - dw) // 2), 635), quote_desc, font=font_why_d, fill='#FFE082', align='center', spacing=16, stroke_width=4, stroke_fill='black')

        # 2. 하단 CTA: 차분한 소프트 쿨 실버 (골드 명언과 완벽 분별) + 네온 골드 버튼
        top_y = 855
        cta_y = 925
        bot_y = 1055
        lead_color = (200, 215, 235)
    else:
        top_y = 920
        cta_y = 990
        bot_y = 1115
        lead_color = 'white'

    top_t = "역사 속 진실이 흥미로웠다면"
    tb = draw.textbbox((0, 0), top_t, font=font_sub_top)
    draw.text((int((CANVAS_W - (tb[2]-tb[0])) // 2), top_y), top_t, font=font_sub_top, fill=lead_color, stroke_width=3, stroke_fill='black')

    cta_t = "좋아요 · 구독"
    cb = draw.textbbox((0, 0), cta_t, font=font_cta_main)
    draw.text((int((CANVAS_W - (cb[2]-cb[0])) // 2), cta_y), cta_t, font=font_cta_main, fill='#FFD700', stroke_width=6, stroke_fill='black')

    bot_t = "매일 만나는 1분 역사 다큐멘터리"
    bb = draw.textbbox((0, 0), bot_t, font=font_sub_bottom)
    draw.text((int((CANVAS_W - (bb[2]-bb[0])) // 2), bot_y), bot_t, font=font_sub_bottom, fill=(235, 242, 255), stroke_width=3, stroke_fill='black')

    draw_credit_safe_zone(draw, credit_str)
    return base_img

# -------------------------------------------------------------
# 7. 본문 씬 렌더러
# -------------------------------------------------------------
def render_body_scene_chunk(bg_path, corner_name, date_title, credit_str, tts_text, audio_path, duration, out_chunk_mp4, temp_dir, zoom_in=True, subtitle_cards=None, caption_str=None, image_type="archive"):
    os.makedirs(temp_dir, exist_ok=True)
    frames = max(1, int(round(duration * FPS)))

    base_img = load_and_fill_fullscreen(bg_path)
    base_img = apply_top_soft_gradient(base_img)
    draw = ImageDraw.Draw(base_img)
    header_bottom_y = draw_body_minimal_header(draw, corner_name, date_title)
    draw_credit_safe_zone(draw, credit_str, caption_str, image_type, start_y=header_bottom_y + 16, center=True)
    base_bg_png = os.path.join(temp_dir, "base_bg.png")
    base_img.convert("RGB").save(base_bg_png, "PNG")

    if subtitle_cards and len(subtitle_cards) > 0:
        timings = [(card["text"], float(card["start"]), float(card["end"])) for card in subtitle_cards]
    else:
        chunks = chunk_text_smart(tts_text, max_length=13)
        timings = calculate_subtitle_timings(chunks, duration)

    sub_png_info = []
    for idx, (c_text, st, en) in enumerate(timings):
        sub_p = os.path.join(temp_dir, f"sub_{idx:02d}.png")
        render_subtitle_png(c_text, sub_p)
        sub_png_info.append((sub_p, st, en))

    zoom_step = 0.08 / max(1, frames)
    vf = []
    if zoom_in:
        vf.append(f"scale=2332:4148,zoompan=z='min(1.0+{zoom_step:.7f}*on,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={CANVAS_W}x{CANVAS_H}:fps={FPS}")
    else:
        vf.append(f"scale=2332:4148,zoompan=z='max(1.08-{zoom_step:.7f}*on,1.0)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={CANVAS_W}x{CANVAS_H}:fps={FPS}")
    vf.append("format=yuv420p")

    for _, st, en in sub_png_info:
        vf.append(f"overlay=(W-w)/2:1260:enable='between(t,{st:.3f},{en:.3f})'")

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

    cover_step = 0.05 / max(1, frames)
    if zoom_in:
        vf = f"scale=2332:4148,zoompan=z='min(1.0+{cover_step:.7f}*on,1.05)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={CANVAS_W}x{CANVAS_H}:fps={FPS},format=yuv420p"
    else:
        vf = f"scale=2332:4148,zoompan=z='max(1.05-{cover_step:.7f}*on,1.0)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={CANVAS_W}x{CANVAS_H}:fps={FPS},format=yuv420p"

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

def assemble_final_shorts(chunk_mp4_list, bgm_mp3, final_output_mp4, temp_dir, bgm_vol=0.14):
    concat_txt = os.path.join(temp_dir, "concat.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for p in chunk_mp4_list:
            f.write(f"file '{p.replace(os.sep, '/')}'\n")

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
        total_dur = int(h)*3600 + int(m_val)*60 + float(s)

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

# -------------------------------------------------------------
# 8. masterpiece_script.json 기반 5개 씬 자동 렌더링 함수
# -------------------------------------------------------------
def render_masterpiece_from_script(target_dir):
    script_p = os.path.join(target_dir, "masterpiece_script.json")
    if not os.path.exists(script_p):
        raise FileNotFoundError(f"대본 파일을 찾을 수 없습니다: {script_p}")

    with open(script_p, "r", encoding="utf-8") as f:
        meta = json.load(f)

    corner_name = meta.get("corner_name", "실록 오늘")
    event_title = meta.get("event_title", "역사 속 오늘")
    bgm_name = meta.get("bgm", "ancient_rite.mp3")

    images_dir = os.path.join(target_dir, "images")
    audio_dir = os.path.join(target_dir, "audio")
    temp_dir = os.path.join(target_dir, "master_render_temp")
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)

    date_basename = os.path.basename(os.path.normpath(target_dir))

    # 대표님의 마스터피스 정규 상단 헤더 규격: 'YYYY. MM. DD 사건제목' (전체 씬 일관 중앙 정렬)
    clean_event_name = re.sub(r'^\d{3,4}년?\s*(선조실록|성종실록|명종실록|실록|조선실록)?,?\s*', '', event_title).strip()
    match_year = re.search(r'\b(\d{3,4})년?\b', event_title)
    year_str = match_year.group(1) if match_year else date_basename[:4]

    # 날짜 파싱 (예: 2026-10-21 또는 20261021)
    digits = re.sub(r'\D', '', date_basename)
    if len(digits) >= 8:
        mm = int(digits[4:6])
        dd = int(digits[6:8])
        master_date_title = f"{year_str}. {mm}. {dd} {clean_event_name}".strip()
    else:
        master_date_title = f"{year_str} {clean_event_name}".strip()

    print("==================================================================")
    print(f"🎬 [마스터피스 렌더링] [{corner_name}] {master_date_title}")
    print(f"   작업 디렉토리: {target_dir}")
    print("==================================================================")

    chunks_list = []
    scenes = meta.get("scenes", [])

    # [Step 0] 0~3초 PRJ_1min_knowledge 표지 인트로 영상 (3.0s, v0 원본 규격 100% 일치)
    cover_bg = os.path.join(images_dir, "scene_1.jpg") if os.path.exists(os.path.join(images_dir, "scene_1.jpg")) else None
    try:
        dt = datetime.strptime(date_basename[:10], "%Y-%m-%d")
        weekday_kr = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"][dt.weekday()]
        date_str = f"{dt.year}년 {dt.month}월 {dt.day}일({weekday_kr})"
    except Exception:
        date_str = f"2026년 10월 21일(수요일)"

    cover_header = f"{date_str} | 1분 {corner_name}"
    highlight_cat = corner_name
    cover_title = meta.get("event_title", master_date_title)
    why_title = "오늘 알아야 할 이유"
    why_desc = meta.get("why_today_desc", meta.get("hook_question", ""))

    print(f"  [Step 0] 0~3초 PRJ_1min_knowledge 표지 인트로 영상 (3.0s)...")
    cover_img = render_intro_cover_image(cover_bg, cover_header, highlight_cat, cover_title, why_title, why_desc)
    cover_mp4 = os.path.join(temp_dir, "part_00_intro_cover.mp4")
    render_cover_chunk(cover_img, 3.0, cover_mp4, zoom_in=True)
    chunks_list.append(cover_mp4)

    # 본문 5개 씬 (scenes 1~5)
    for idx, sc in enumerate(scenes):
        s_num = sc.get("scene_number", idx + 1)
        script_text = sc.get("script", "")
        img_p = os.path.join(images_dir, f"scene_{s_num}.jpg")
        audio_p = os.path.join(audio_dir, f"scene{s_num}.mp3")

        dur = get_audio_duration(audio_p)
        image_type = sc.get("image_type", "archive")
        caption = sc.get("image_caption") or sc.get("display_title", "")

        custom_credit = sc.get("credit") or meta.get("credit")
        if custom_credit:
            credit = custom_credit
        elif image_type == "ai_generated":
            credit = "제작: Vertex AI 시각 복원 / 역사 고증 일러스트"
        elif "실록" in corner_name or "실록" in master_date_title:
            credit = "출처: 조선왕조실록 국역본 / 국사편찬위원회"
        else:
            credit = "출처: 역사 기록 사료 / 위키미디어 커먼즈"

        print(f"  [Step {idx+1}] 씬 {s_num}: {dur:.1f}s - {master_date_title}...")
        sc_mp4 = os.path.join(temp_dir, f"part_{s_num:02d}.mp4")
        sc_tmp = os.path.join(temp_dir, f"tmp_{s_num}")
        render_body_scene_chunk(
            bg_path=img_p,
            corner_name=corner_name,
            date_title=master_date_title,
            credit_str=credit,
            tts_text=script_text,
            audio_path=audio_p,
            duration=dur,
            out_chunk_mp4=sc_mp4,
            temp_dir=sc_tmp,
            zoom_in=(idx % 2 == 0),
            caption_str=caption,
            image_type=image_type
        )
        chunks_list.append(sc_mp4)

    # [마지막 3초] 정갈한 아웃트로 피날레 (상단에 '오늘 알아야 할 이유' 교훈 조화롭게 배치)
    print("  [Step 6] 정갈한 아웃트로 피날레 렌더링 (3.0s)...")
    last_img = os.path.join(images_dir, f"scene_{len(scenes)}.jpg") if scenes else os.path.join(images_dir, "scene_1.jpg")
    outro_img = render_outro_finale_image(last_img, "1분 역사 다큐멘터리 아카이브", why_title=why_title, why_desc=why_desc)
    outro_mp4 = os.path.join(temp_dir, "part_99_outro_finale.mp4")
    render_cover_chunk(outro_img, 3.0, outro_mp4, zoom_in=False)
    chunks_list.append(outro_mp4)

    # 결합 및 합성 (골드바 + BGM 오토덕킹)
    print("  [Step 7] Concat + BGM 오토덕킹 + 상단 6px 골드 진행선 바 합성...")
    bgm_path = os.path.join(BGM_DIR, bgm_name)
    if not os.path.exists(bgm_path):
        bgm_path = os.path.join(BGM_DIR, "ancient_rite.mp3")
    if not os.path.exists(bgm_path):
        bgm_path = os.path.join(BGM_DIR, "bgm_history_epic.mp3")

    clean_corner = corner_name.replace(" ", "_")
    final_output = os.path.join(target_dir, f"{date_basename}_{clean_corner}_마스터피스_완성본.mp4")
    total_sec = assemble_final_shorts(chunks_list, bgm_path, final_output, temp_dir, bgm_vol=0.22)
    file_size_mb = os.path.getsize(final_output) / (1024 * 1024)

    print(f"\n🎉 [완성] {final_output}")
    print(f"  총 재생시간: {total_sec:.2f}초 | 파일 크기: {file_size_mb:.2f} MB")
    return final_output

if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1].strip().strip('"').strip("'")
        if os.path.isdir(arg):
            target_dir = arg
        elif os.path.isdir(os.path.join(BASE_DIR, "data", "history", arg)):
            target_dir = os.path.join(BASE_DIR, "data", "history", arg)
        else:
            target_dir = arg
    else:
        kst = timezone(timedelta(hours=9))
        now = datetime.now(kst)
        today_dash = now.strftime("%Y-%m-%d")
        target_dir = os.path.join(BASE_DIR, "data", "history", today_dash)
        if not os.path.exists(target_dir):
            fallback_sample = os.path.join(BASE_DIR, "data", "history", "2026-10-21")
            if os.path.exists(fallback_sample):
                target_dir = fallback_sample

    print(f"🚀 실행 대상 디렉토리: {target_dir}")
    render_masterpiece_from_script(target_dir)
