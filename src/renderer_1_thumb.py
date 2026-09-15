import json
import os
import sys
import re
from datetime import datetime
import inquirer
from moviepy.editor import *
from PIL import Image, ImageDraw, ImageFont
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import get_daily_dir, CONFIG_DIR, EDITION_CONFIG

def split_title_smart(title_text):
    words = title_text.split()
    if len(words) <= 1:
        return title_text
        
    match = re.search(r'(\.{2,}|…)\s*', title_text)
    if match:
        idx = match.end()
        return title_text[:match.start()].strip() + "\n" + title_text[idx:].strip()
            
    match = re.search(r'(-|,)\s*', title_text)
    if match:
        idx = match.end()
        if 0.2 < (idx / len(title_text)) < 0.8:
            return title_text[:idx].strip() + "\n" + title_text[idx:].strip()

    match = re.search(r'([\'"\]])\s+', title_text)
    if match:
        idx = match.end()
        if 0.2 < (idx / len(title_text)) < 0.8:
            return title_text[:idx].strip() + "\n" + title_text[idx:].strip()

    mid_idx = len(words) // 2
    best_idx = mid_idx
    particles = ['은', '는', '이', '가', '을', '를', '다', '고', '며', '서', '게', '에']
    
    for offset in [0, -1, 1, -2, 2]:
        check_idx = mid_idx + offset
        if 0 < check_idx < len(words):
            word_before = words[check_idx-1]
            if any(word_before.endswith(p) for p in particles):
                best_idx = check_idx
                break
                
    if best_idx != mid_idx:
        return " ".join(words[:best_idx]) + "\n" + " ".join(words[best_idx:])
        
    best_diff = float('inf')
    best_split = mid_idx
    
    for i in range(1, len(words)):
        str_front = " ".join(words[:i])
        str_back = " ".join(words[i:])
        diff = abs(len(str_front) - len(str_back))
        if diff < best_diff:
            best_diff = diff
            best_split = i
            
    return " ".join(words[:best_split]) + "\n" + " ".join(words[best_split:])

def create_pil_text_clip(text, font_path, fontsize, temp_dir, text_type="title", source_text="", date_str="", top_title=""):
    try:
        font = ImageFont.truetype(font_path, fontsize)
    except IOError:
        font = ImageFont.load_default()
        
    canvas_w = 1080
    
    if text_type == "watermark":
        canvas_h = 100
    elif text_type == "header":
        canvas_h = 100
    elif text_type == "title":
        canvas_h = 320 
    elif text_type in ["quote", "hook"]:
        canvas_h = 1070
    else: 
        canvas_h = 200
        
    img = Image.new('RGBA', (canvas_w, canvas_h), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    if text_type == "watermark":
        x, y = 40, 40
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 180))
    elif text_type == "header":
        bbox = draw.textbbox((0, 0), text, font=font)
        x = (canvas_w - (bbox[2] - bbox[0])) / 2
        y = (canvas_h - (bbox[3] - bbox[1])) / 2
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 220))
    elif text_type == "quote":
        lines = text.split('\n')
        wrapped_lines = []
        for line in lines:
            if not line.strip():
                wrapped_lines.append("")
                continue
            words = line.split()
            current_line = []
            for word in words:
                test_line = " ".join(current_line + [word])
                bbox = draw.textbbox((0, 0), test_line, font=font)
                if (bbox[2] - bbox[0]) > 950:
                    wrapped_lines.append(" ".join(current_line))
                    current_line = [word]
                else:
                    current_line.append(word)
            if current_line:
                wrapped_lines.append(" ".join(current_line))
                
        total_h = 0
        line_heights = []
        for line in wrapped_lines:
            if not line:
                h = 40
            else:
                bbox = draw.textbbox((0, 0), line, font=font)
                h = bbox[3] - bbox[1]
            line_heights.append(h)
            total_h += h + 20
            
        current_y = (canvas_h - total_h) / 2
        for i, line in enumerate(wrapped_lines):
            if not line:
                current_y += line_heights[i] + 20
                continue
            bbox = draw.textbbox((0, 0), line, font=font)
            line_w = bbox[2] - bbox[0]
            x = (canvas_w - line_w) / 2
            
            fill_color = 'white' if line.startswith('- ') else '#FFD700'
            draw.text((x, current_y), line, font=font, fill=fill_color, stroke_width=2, stroke_fill='black')
            current_y += line_heights[i] + 20
    elif text_type == "hook":
        try:
            font_title = ImageFont.truetype(font_path, 90)
            font_date = ImageFont.truetype(font_path, 40)
            font_top = ImageFont.truetype(font_path, 70)
        except IOError:
            font_title = font
            font_date = font
            font_top = font
            
        if date_str:
            bbox_d = draw.textbbox((0, 0), date_str, font=font_date)
            date_h = bbox_d[3] - bbox_d[1]
        else:
            date_h = 0
            
        if top_title:
            bbox_top = draw.textbbox((0, 0), top_title, font=font_top)
            top_h = bbox_top[3] - bbox_top[1]
        else:
            top_h = 0
            
        lines = text.split('\n')
        wrapped_lines = []
        for line in lines:
            words = line.split()
            current_line = []
            for word in words:
                test_line = " ".join(current_line + [word])
                bbox = draw.textbbox((0, 0), test_line, font=font_title)
                if (bbox[2] - bbox[0]) > 950:
                    wrapped_lines.append(" ".join(current_line))
                    current_line = [word]
                else:
                    current_line.append(word)
            if current_line:
                wrapped_lines.append(" ".join(current_line))
                
        final_text = "\n".join(wrapped_lines)
        bbox_t = draw.multiline_textbbox((0, 0), final_text, font=font_title, spacing=20)
        title_h = bbox_t[3] - bbox_t[1]
        
        total_h = date_h + (30 if date_str else 0) + top_h + (50 if top_title else 0) + title_h
        current_y = (canvas_h - total_h) / 2
        
        if date_str:
            bbox_d = draw.textbbox((0, 0), date_str, font=font_date)
            x_d = (canvas_w - (bbox_d[2] - bbox_d[0])) / 2
            draw.text((x_d, current_y), date_str, font=font_date, fill='white')
            current_y += date_h + 30
            
        if top_title:
            bbox_top = draw.textbbox((0, 0), top_title, font=font_top)
            x_top = (canvas_w - (bbox_top[2] - bbox_top[0])) / 2
            draw.text((x_top, current_y), top_title, font=font_top, fill='#FFFFFF', stroke_width=2, stroke_fill='black')
            current_y += top_h + 50
            
        bbox_t = draw.multiline_textbbox((0, 0), final_text, font=font_title, spacing=20)
        x_t = (canvas_w - (bbox_t[2] - bbox_t[0])) / 2
        draw.multiline_text((x_t, current_y), final_text, font=font_title, fill='#FFD700', align='center', spacing=20, stroke_width=3, stroke_fill='black')
        
    elif text_type == "title":
        max_w = 950
        lines = text.split('\n')
        truncated_lines = []
        
        try:
            font_main = ImageFont.truetype(font_path, 65)
            font_source = ImageFont.truetype(font_path, 50)
        except IOError:
            font_main = font
            font_source = font
        
        for line in lines:
            base_line = line
            bbox = draw.textbbox((0, 0), base_line, font=font_main)
            line_w = bbox[2] - bbox[0]
            
            if line_w > max_w:
                while len(base_line) > 0:
                    base_line = base_line[:-1]
                    test_str = base_line + "..."
                    bbox = draw.textbbox((0, 0), test_str, font=font_main)
                    if (bbox[2] - bbox[0]) <= max_w:
                        break
                truncated_lines.append(base_line + "...")
            else:
                truncated_lines.append(line)
                
        if len(truncated_lines) > 2:
            truncated_lines = truncated_lines[:2]
                
        total_h = 0
        line_heights = []
        
        for line in truncated_lines:
            bbox = draw.textbbox((0, 0), line, font=font_main)
            h = bbox[3] - bbox[1]
            line_heights.append(h)
            total_h += h + 10
            
        source_str = f"출처: {source_text}" if source_text and source_text != 'Unknown' else ""
        if source_str:
            bbox = draw.textbbox((0, 0), source_str, font=font_source)
            h_src = bbox[3] - bbox[1]
            line_heights.append(h_src)
            total_h += h_src + 20
            
        current_y = (canvas_h - total_h) / 2
        
        for i, line in enumerate(truncated_lines):
            bbox = draw.textbbox((0, 0), line, font=font_main)
            line_w = bbox[2] - bbox[0]
            x = (canvas_w - line_w) / 2
            draw.text((x, current_y), line, font=font_main, fill='#FFD700', stroke_width=2, stroke_fill='black')
            current_y += line_heights[i] + 10
            
        if source_str:
            current_y += 10
            bbox = draw.textbbox((0, 0), source_str, font=font_source)
            line_w = bbox[2] - bbox[0]
            x = (canvas_w - line_w) / 2
            draw.text((x, current_y), source_str, font=font_source, fill=(200, 200, 200, 255))
            
    temp_path = os.path.join(temp_dir, f"temp_{abs(hash(text))}.png")
    img.save(temp_path)
    
    clip = ImageClip(temp_path)
    return clip

def make_bg_clip(img_path, source_text, title_text, font_path, temp_dir, part_name=None, center_text=None, date_str="", top_title=""):
    from config import ASSETS_DIR
    vintage_bg_path = os.path.join(ASSETS_DIR, "vintage_bg.jpg")
    
    if os.path.exists(vintage_bg_path):
        bg_pil = Image.open(vintage_bg_path).convert('RGB')
        bg_np = np.array(bg_pil)
        bg = ImageClip(bg_np)
        bg = bg.resize(width=1080)
        if bg.h < 1920:
            bg = bg.resize(height=1920)
        bg = bg.crop(x_center=bg.w/2, y_center=bg.h/2, width=1080, height=1920)
    else:
        bg = ColorClip(size=(1080, 1920), color=(25, 25, 25))
        
    layers = [bg]
    if os.path.exists(vintage_bg_path):
        layers.append(ColorClip(size=(1080, 1920), color=(0, 0, 0)).set_opacity(0.65))
    
    if img_path and os.path.exists(img_path):
        img_pil = Image.open(img_path).convert('RGB')
        img_np = np.array(img_pil)
        clip = ImageClip(img_np)
        target_ratio = 1080 / 1070
        clip_ratio = clip.w / clip.h
        
        if clip.aspect_ratio > 1080/850:
            clip = clip.resize(height=850)
        else:
            clip = clip.resize(width=1080)
            
        clip = clip.crop(x_center=clip.w/2, y_center=clip.h/2, width=1080, height=850)
        clip = clip.set_position(("center", 470))
        layers.append(clip)
        
    if center_text:
        if part_name == "hook":
            center_clip = create_pil_text_clip(center_text, font_path, 90, temp_dir, text_type="hook", date_str=date_str, top_title=top_title)
        elif part_name == "closing":
            if "-" in center_text:
                parts = center_text.rsplit("-", 1)
                center_text = f'"{parts[0].strip()}"\n\n- {parts[1].strip()}'
            elif "–" in center_text:
                parts = center_text.rsplit("–", 1)
                center_text = f'"{parts[0].strip()}"\n\n- {parts[1].strip()}'
            else:
                center_text = f'"{center_text.strip()}"'
            center_clip = create_pil_text_clip(center_text, font_path, 60, temp_dir, text_type="quote")
        else:
            center_clip = None
            
        if center_clip:
            center_clip = center_clip.set_position(("center", 470))
            layers.append(center_clip)
        
    if title_text:
        clean_title = re.sub(r'\[.*?\]', '', title_text).strip()
        split_title = split_title_smart(clean_title)
        title_clip = create_pil_text_clip(split_title, font_path, 65, temp_dir, text_type="title", source_text=source_text)
        title_clip = title_clip.set_position(("center", 150))
        layers.append(title_clip)
        
    if part_name != "hook" and date_str and top_title:
        header_text = f"{date_str}  |  {top_title}"
        header_clip = create_pil_text_clip(header_text, font_path, 40, temp_dir, text_type="header")
        header_clip = header_clip.set_position(("center", 100))
        layers.append(header_clip)
            
    final_bg_clip = CompositeVideoClip(layers, size=(1080, 1920))
    return final_bg_clip

def run_renderer_thumb(target_date=None, edition='morning'):
    daily_dir = get_daily_dir(target_date, edition)
    script_path = os.path.join(daily_dir, "3_script.json")
    articles_path = os.path.join(daily_dir, "2_selected_articles.json")
    font_path = os.path.join(CONFIG_DIR, "GmarketSansTTFBold.ttf")
    
    temp_dir = os.path.join(daily_dir, "temp_subs")
    os.makedirs(temp_dir, exist_ok=True)
    
    if not os.path.exists(script_path):
        print(f"Missing {script_path}")
        return None
        
    with open(script_path, "r", encoding="utf-8") as f:
        script_data = json.load(f)
        
    articles_data = []
    if os.path.exists(articles_path):
        with open(articles_path, "r", encoding="utf-8") as f:
            articles_data = json.load(f)
            
    parts = ["hook", "issue1", "issue2", "issue3", "closing"]
    
    print("Building thumbnail images...")
    
    date_parts = os.path.basename(daily_dir).split('-')
    if len(date_parts) == 3:
        dt = datetime(int(date_parts[0]), int(date_parts[1]), int(date_parts[2]))
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        weekday = weekdays[dt.weekday()]
        today_full_date = f"{date_parts[0]}년 {int(date_parts[1])}월 {int(date_parts[2])}일 ({weekday})"
        month_day_str = f"{int(date_parts[1])}월 {int(date_parts[2])}일"
    else:
        today_full_date = ""
        month_day_str = ""
        
    top_title = EDITION_CONFIG[edition]["top_title"]
    
    for part in parts:
        if part not in script_data:
            continue
            
        img_path = None
        source_text = None
        title_text = None
        display_date_str = today_full_date
        
        if part.startswith("issue"):
            idx = int(part[-1]) - 1 
            if idx < len(articles_data):
                article = articles_data[idx]
                img_path = article.get("image_path")
                source_text = article.get("source")
                title_text = script_data.get(f"{part}_title", article.get("text"))
                event_year = article.get("year")
                if event_year and month_day_str:
                    display_date_str = f"{event_year}년 {month_day_str}"
                
                # 강제로 노란색 타이틀 끝에 (연도) 추가
                if event_year and f"({event_year})" not in title_text:
                    title_text = f"{title_text} ({event_year})"
                
        center_text = None
        if part == "closing":
            center_text = script_data.get("closing_quote")
        elif part == "hook":
            center_text = script_data.get("hook_title")
                
        bg_clip = make_bg_clip(img_path, source_text, title_text, font_path, temp_dir, part_name=part, center_text=center_text, date_str=display_date_str, top_title=top_title)
        
        thumb_path = os.path.join(daily_dir, f"6_thumb_{part}.png")
        bg_clip.save_frame(thumb_path, t=0.0)
        print(f"  -> Thumbnail saved: {thumb_path}")
            
    print("All thumbnails generated successfully.")

if __name__ == "__main__":
    from config import DATA_DIR
    available_folders = []
    if os.path.exists(DATA_DIR):
        available_folders = [d for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d))]
        
    if not available_folders:
        print("생성된 데이터 폴더가 없습니다. scraper.py를 먼저 실행하세요.")
        sys.exit(1)
        
    available_folders.sort(reverse=True)
    
    questions = [
        inquirer.List('target_folder',
                      message="[renderer_1_thumb.py 독립 실행] 작업할 대상 날짜(폴더)를 선택하세요:",
                      choices=available_folders,
                  ),
    ]
    answers = inquirer.prompt(questions)
    
    if answers:
        selected_folder = answers['target_folder']
        target_date = selected_folder.replace("-", "")
        print(f"Target Date: {target_date}")
        run_renderer_thumb(target_date)
