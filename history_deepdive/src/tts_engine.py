import os
import sys
import json
import re
import time
from google.cloud import texttospeech

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, 'config')
CRED_PATH = os.path.join(CONFIG_DIR, 'application_default_credentials.json')
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CRED_PATH


def clean_tts_text(text: str) -> str:
    """음성 합성 실패를 막기 위해 특수기호나 따옴표 정리"""
    text = re.sub(r'["\'`“”‘’]', '', text)
    text = re.sub(r'[\(\)\[\]]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def synthesize_with_retry(client, text, voice_name, speaking_rate, pitch, max_retries=2):
    for attempt in range(max_retries + 1):
        try:
            voice_params = texttospeech.VoiceSelectionParams(
                language_code="ko-KR",
                name=voice_name
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=speaking_rate,
                pitch=pitch
            )
            synthesis_input = texttospeech.SynthesisInput(text=text)
            return client.synthesize_speech(
                input=synthesis_input, voice=voice_params, audio_config=audio_config
            )
        except Exception as e:
            err_str = str(e)
            if attempt < max_retries:
                wait_sec = 3 * (attempt + 1)
                print(f"    ⏳ [TTS 재시도 대기] {wait_sec}초 후 재시도 중 ({attempt+1}/{max_retries})... ({err_str[:60]})")
                time.sleep(wait_sec)
            else:
                fallback_voice = "ko-KR-Neural2-C" if voice_name != "ko-KR-Neural2-C" else "ko-KR-Neural2-A"
                print(f"    🔄 [TTS 안전 폴백] 성우 전환 ({voice_name} -> {fallback_voice})...")
                voice_params = texttospeech.VoiceSelectionParams(
                    language_code="ko-KR",
                    name=fallback_voice
                )
                audio_config = texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MP3,
                    speaking_rate=speaking_rate,
                    pitch=pitch
                )
                synthesis_input = texttospeech.SynthesisInput(text=text)
                return client.synthesize_speech(
                    input=synthesis_input, voice=voice_params, audio_config=audio_config
                )


def generate_scene_audios(script_data: dict, preset: dict, out_dir: str):
    audio_dir = os.path.join(out_dir, "audio")
    os.makedirs(audio_dir, exist_ok=True)

    voice_name = preset.get("voice", "ko-KR-Neural2-C")
    speaking_rate = preset.get("speaking_rate", 1.0)
    pitch = preset.get("pitch", 0.0)

    print(f"\n[음성 합성 엔진] Google Cloud Neural2 - 성우: {voice_name} (속도: {speaking_rate}x, 피치: {pitch})")

    client = texttospeech.TextToSpeechClient()
    scenes = script_data.get("scenes", [])

    for idx, sc in enumerate(scenes):
        s_num = sc.get("scene_number", idx + 1)
        raw_script = sc.get("script", "").strip()
        script_text = clean_tts_text(raw_script)

        dest_audio = os.path.join(audio_dir, f"scene{s_num}.mp3")

        # 씬 간 1.5초 대기 버퍼 (연속 요청에 의한 400/429 제약 원천 차단)
        if idx > 0:
            time.sleep(1.5)

        print(f"  🎙️ [Scene {s_num}] 음성 합성: '{script_text[:30]}...'")
        response = synthesize_with_retry(client, script_text, voice_name, speaking_rate, pitch)
        with open(dest_audio, "wb") as f_out:
            f_out.write(response.audio_content)

    print(f"  ✅ 5개 씬 Neural2 음성 합성 완료.")
