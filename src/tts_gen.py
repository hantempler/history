import os
import json
import sys
from google.cloud import texttospeech
import inquirer

# Add src to Python path if run standalone
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import get_daily_dir, EDITION_CONFIG

def run_tts_gen(target_date, edition='morning'):
    daily_dir = get_daily_dir(target_date, edition)
    script_path = os.path.join(daily_dir, "3_script.json")
    
    if not os.path.exists(script_path):
        print(f"Script not found at {script_path}. Run script_gen first.")
        return None
        
    with open(script_path, "r", encoding="utf-8") as f:
        try:
            script_data = json.load(f)
        except json.JSONDecodeError:
            print("Failed to decode JSON from 3_script.json")
            return None

    # Google Cloud TTS 클라이언트 초기화
    try:
        client = texttospeech.TextToSpeechClient()
    except Exception as e:
        print(f"Failed to initialize TTS client: {e}")
        print("Make sure GOOGLE_APPLICATION_CREDENTIALS is set.")
        return None

    # TTS 음색 설정 (한국어 여성 음성 - 출근길 감성)
    voice = texttospeech.VoiceSelectionParams(
        language_code="ko-KR",
        name=EDITION_CONFIG[edition]["voice_name"] 
    )
    
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=1.05, # 속도감 있게 전달
        pitch=0.0
    )

    print("Generating 5 separate audio files...")
    
    keys_to_generate = ["hook", "issue1", "issue2", "issue3", "closing"]
    
    for key in keys_to_generate:
        text = script_data.get(key, "")
        if not text:
            continue
            
        synthesis_input = texttospeech.SynthesisInput(text=text)
        
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        
        output_filename = f"4_audio_{key}.mp3"
        output_path = os.path.join(daily_dir, output_filename)
        
        with open(output_path, "wb") as out:
            out.write(response.audio_content)
            print(f"  -> Audio for {key} saved to {output_path}")

if __name__ == "__main__":
    from config import DATA_DIR
    available_folders = []
    if os.path.exists(DATA_DIR):
        available_folders = [d for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d))]
    
    if not available_folders:
        print("생성된 데이터 폴더가 없습니다. script_gen.py를 먼저 실행하세요.")
        sys.exit(1)
        
    available_folders.sort(reverse=True)
    
    questions = [
        inquirer.List('target_folder',
                      message="[tts_gen.py 독립 실행] 작업할 대상 날짜(폴더)를 선택하세요:",
                      choices=available_folders,
                  ),
    ]
    answers = inquirer.prompt(questions)
    
    if answers:
        selected_folder = answers['target_folder']
        target_date = selected_folder.replace("-", "")
        print(f"Target Date: {target_date}")
        run_tts_gen(target_date)
