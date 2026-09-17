import json
import os
import sys
import re
from datetime import datetime
import inquirer
from moviepy.editor import *
from PIL import Image, ImageDraw, ImageFont

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import get_daily_dir, CONFIG_DIR, EDITION_CONFIG

def chunk_text(text, max_length=15):
    lines = text.replace('\n', ' ').split()
    chunks = []
    current_line = []
    current_chunk_lines = []
    
    for word in lines:
        if sum(len(w) for w in current_line) + len(current_line) + len(word) > 24:
            if current_line:
                current_chunk_lines.append(" ".join(current_line))
            current_line = [word]
            if len(current_chunk_lines) == 2:
                chunks.append("\n".join(current_chunk_lines))
                current_chunk_lines = []
        else:
            current_line.append(word)
            
    if current_line:
        current_chunk_lines.append(" ".join(current_line))
    if current_chunk_lines:
        chunks.append("\n".join(current_chunk_lines))
        
    return chunks

def create_pil_subtitle_clip(text, font_path, fontsize, temp_dir):
    try:
        font = ImageFont.truetype(font_path, fontsize)
    except IOError:
        font = ImageFont.load_default()
        
    canvas_w, canvas_h = 1080, 200
    img = Image.new('RGBA', (canvas_w, canvas_h), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=10)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    x = (canvas_w - text_w) / 2
    y = (canvas_h - text_h) / 2
    draw.multiline_text((x, y), text, font=font, fill='white', align='center', spacing=10, stroke_width=3, stroke_fill='black')
    
    temp_path = os.path.join(temp_dir, f"temp_{abs(hash(text))}.png")
    img.save(temp_path)
    
    clip = ImageClip(temp_path)
    return clip

def run_renderer_video(target_date=None, edition='morning'):
    if target_date is None:
        target_date = datetime.now().strftime("%Y%m%d")
    daily_dir = get_daily_dir(target_date, edition)
    script_path = os.path.join(daily_dir, "3_script.json")
    font_path = os.path.join(CONFIG_DIR, "GmarketSansTTFBold.ttf")
    
    temp_dir = os.path.join(daily_dir, "temp_subs")
    os.makedirs(temp_dir, exist_ok=True)
    
    if not os.path.exists(script_path):
        print(f"Missing {script_path}")
        return None
        
    with open(script_path, "r", encoding="utf-8") as f:
        script_data = json.load(f)
            
    parts = ["hook", "issue1", "issue2", "issue3", "closing"]
    clips = []
    
    print("Building final video from thumbnails and audio...")
    
    for part in parts:
        if part not in script_data:
            continue
            
        text = script_data[part]
        audio_path = os.path.join(daily_dir, f"4_audio_{part}.mp3")
        thumb_path = os.path.join(daily_dir, f"6_thumb_{part}.png")
        
        if not os.path.exists(audio_path) or not os.path.exists(thumb_path):
            print(f"Missing audio or thumb for {part}. Skipping.")
            continue
            
        audio = AudioFileClip(audio_path)
        duration = audio.duration
        
        bg_clip = ImageClip(thumb_path).set_duration(duration)
        bg_clip = bg_clip.set_position(('center', 'center'))
        
        subtitle_clips = []
        if part.startswith("issue"):
            chunks = chunk_text(text, max_length=15)
            total_chars = sum(len(c.replace('\n', ' ').replace(' ', '')) for c in chunks)
            if total_chars == 0:
                total_chars = 1
                
            current_time = 0
            for chunk in chunks:
                chunk_chars = len(chunk.replace('\n', ' ').replace(' ', ''))
                if chunk_chars == 0:
                    continue
                    
                chunk_duration = duration * (chunk_chars / total_chars)
                txt_clip = create_pil_subtitle_clip(chunk, font_path, 70, temp_dir)
                txt_clip = txt_clip.set_duration(chunk_duration)
                txt_clip = txt_clip.set_position(('center', 1350))
                txt_clip = txt_clip.set_start(current_time)
                subtitle_clips.append(txt_clip)
                current_time += chunk_duration
                
        final_clip = CompositeVideoClip([bg_clip] + subtitle_clips).set_duration(duration)
        final_clip = final_clip.set_audio(audio)
        clips.append(final_clip)
            
    if not clips:
        print("No valid clips generated.")
        return None
        
    print("Concatenating all clips...")
    final_video = concatenate_videoclips(clips)
    
    output_path = os.path.join(daily_dir, f"{target_date}{EDITION_CONFIG[edition]['video_suffix']}")
    print(f"Rendering final video to {output_path} (Ultra-fast Mode)...")
    
    final_video.write_videofile(
        output_path, 
        fps=15,
        preset="ultrafast",
        codec="libx264", 
        audio_codec="aac",
        threads=4,
        logger='bar'
    )
    print(f"Video saved to {output_path}")
    return output_path

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
                      message="[renderer_2_video.py 독립 실행] 작업할 대상 날짜(폴더)를 선택하세요:",
                      choices=available_folders,
                  ),
    ]
    answers = inquirer.prompt(questions)
    
    if answers:
        selected_folder = answers['target_folder']
        target_date = selected_folder.replace("-", "")
        print(f"Target Date: {target_date}")
        run_renderer_video(target_date)
