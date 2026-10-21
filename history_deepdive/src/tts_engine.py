import os
import sys
import json
from google.cloud import texttospeech

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, 'config')
CRED_PATH = os.path.join(CONFIG_DIR, 'application_default_credentials.json')
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CRED_PATH


def generate_scene_audios(script_data: dict, preset: dict, out_dir: str):
    audio_dir = os.path.join(out_dir, "audio")
    os.makedirs(audio_dir, exist_ok=True)

    voice_name = preset.get("voice", "ko-KR-Neural2-C")
    speaking_rate = preset.get("speaking_rate", 1.0)
    pitch = preset.get("pitch", 0.0)

    print(f"\n[음성 합성 엔진] Google Cloud Neural2 - 성우: {voice_name} (속도: {speaking_rate}x, 피치: {pitch})")

    client = texttospeech.TextToSpeechClient()
    voice_params = texttospeech.VoiceSelectionParams(
        language_code="ko-KR",
        name=voice_name
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=speaking_rate,
        pitch=pitch
    )

    scenes = script_data.get("scenes", [])
    for idx, sc in enumerate(scenes):
        s_num = sc.get("scene_number", idx + 1)
        script_text = sc.get("script", "").strip()
        dest_audio = os.path.join(audio_dir, f"scene{s_num}.mp3")

        print(f"  🎙️ [Scene {s_num}] 음성 합성: '{script_text[:30]}...'")
        synthesis_input = texttospeech.SynthesisInput(text=script_text)
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice_params, audio_config=audio_config
        )
        with open(dest_audio, "wb") as f_out:
            f_out.write(response.audio_content)

    print(f"  ✅ 5개 씬 Neural2 음성 합성 완료.")
