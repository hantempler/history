import os
import sys
import json
import re
import time
import subprocess
from xml.sax.saxutils import escape
from google.cloud import texttospeech_v1beta1 as texttospeech

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.config import get_daily_dir, CONFIG_DIR

CRED_PATH = os.path.join(CONFIG_DIR, 'application_default_credentials.json')
if os.path.exists(CRED_PATH):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CRED_PATH


def get_audio_duration_probe(audio_path: str) -> float:
    """ffprobe 또는 ffmpeg로 오디오 실제 길이(초) 측정."""
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if res.returncode == 0 and res.stdout.strip():
            return float(res.stdout.strip())
    except Exception:
        pass

    try:
        cmd = ["ffmpeg", "-i", str(audio_path)]
        p = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", p.stderr)
        if m:
            h, m_val, s = m.groups()
            return int(h) * 3600 + int(m_val) * 60 + float(s)
    except Exception:
        pass
    return 10.0


def clean_tts_text(text: str) -> str:
    """음성 합성 실패를 막기 위해 특수기호나 따옴표 정리"""
    text = re.sub(r'["\'`“”‘’]', '', text)
    text = re.sub(r'[\(\)\[\]]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def synthesize_ssml_with_timepoints(client, ssml, voice_name, pitch, language_code="ko-KR", fallback_voice=None, max_retries=2):
    """Google Cloud TTS SSML_MARK timepoints 정밀 요청 및 재시도."""
    for attempt in range(max_retries + 1):
        try:
            voice_params = texttospeech.VoiceSelectionParams(
                language_code=language_code,
                name=voice_name
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                pitch=pitch
            )
            synthesis_input = texttospeech.SynthesisInput(ssml=ssml)
            request = texttospeech.SynthesizeSpeechRequest(
                input=synthesis_input,
                voice=voice_params,
                audio_config=audio_config,
                enable_time_pointing=[texttospeech.SynthesizeSpeechRequest.TimepointType.SSML_MARK]
            )
            return client.synthesize_speech(request=request)
        except Exception as e:
            err_str = str(e)
            if attempt < max_retries:
                wait_sec = 3 * (attempt + 1)
                print(f"    ⏳ [TTS 재시도 대기] {wait_sec}초 후 재시도 중 ({attempt+1}/{max_retries})... ({err_str[:60]})")
                time.sleep(wait_sec)
            else:
                fb_voice = fallback_voice or ("ko-KR-Neural2-A" if "ko" in language_code else "en-US-Journey-F")
                print(f"    🔄 [TTS 안전 폴백] 성우 전환 ({voice_name} -> {fb_voice})...")
                voice_params = texttospeech.VoiceSelectionParams(
                    language_code=language_code,
                    name=fb_voice
                )
                audio_config = texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MP3,
                    pitch=pitch
                )
                synthesis_input = texttospeech.SynthesisInput(ssml=ssml)
                request = texttospeech.SynthesizeSpeechRequest(
                    input=synthesis_input,
                    voice=voice_params,
                    audio_config=audio_config,
                    enable_time_pointing=[texttospeech.SynthesizeSpeechRequest.TimepointType.SSML_MARK]
                )
                return client.synthesize_speech(request=request)


def generate_scene_audios(script_data: dict, out_dir: str, edition="history"):
    audio_dir = os.path.join(out_dir, "audio")
    os.makedirs(audio_dir, exist_ok=True)

    is_english = edition in ("history_en", "en") or script_data.get("lang") == "en"
    lang = "en" if is_english else "ko"

    if is_english:
        language_code = "en-US"
        voice_name = "en-US-Neural2-J"
        fallback_voice = "en-US-Journey-F"
        speaking_rate = 1.03
        pitch = 0.0
    else:
        language_code = "ko-KR"
        voice_name = "ko-KR-Neural2-C"
        fallback_voice = "ko-KR-Neural2-A"
        speaking_rate = 1.05
        pitch = -0.5

    rate_pct = f"{int(speaking_rate * 100)}%"
    print(f"\n[음성 합성 엔진] Google Cloud Neural2 SSML Timepoint 가동")
    print(f"  언어: {language_code}, 성우: {voice_name} (속도: {rate_pct}, 피치: {pitch})")

    # 1. 씬별 호흡 단위 다이내믹 청킹 분석
    from src.subtitle_engine import analyze_dynamic_chunks, rule_based_chunking, calculate_weighted_timings
    scenes = script_data.get("scenes", [])
    has_existing_chunks = all(bool(sc.get("chunks")) and isinstance(sc.get("chunks"), list) and len(sc.get("chunks")) > 0 for sc in scenes)
    if has_existing_chunks:
        print(f"  🔍 [Timepoint] 대본 내 기존 청크 구조를 재사용합니다 ({len(scenes)}씬).")
        analyzed_map = {s.get("scene_number", s.get("scene_no", idx+1)): s.get("chunks", []) for idx, s in enumerate(scenes)}
    else:
        print(f"  🔍 [Timepoint] 씬별 다이내믹 자막 청크 분석 중 ({len(scenes)}씬)...")
        analyzed_scenes = analyze_dynamic_chunks(scenes, lang=lang)
        analyzed_map = {s.get("scene_number", s.get("scene_no", idx+1)): s.get("chunks", []) for idx, s in enumerate(analyzed_scenes)}

    client = texttospeech.TextToSpeechClient()

    for idx, sc in enumerate(scenes):
        s_num = sc.get("scene_number", idx + 1)
        raw_script = sc.get("script", "").strip()
        script_text = clean_tts_text(raw_script)

        dest_audio = os.path.join(audio_dir, f"scene{s_num}.mp3")
        tp_file_audio = os.path.join(audio_dir, f"timepoints_scene{s_num}.json")
        tp_file_out = os.path.join(out_dir, f"timepoints_scene{s_num}.json")

        scene_chunks = analyzed_map.get(s_num, [])
        if not scene_chunks:
            scene_chunks = rule_based_chunking(script_text, lang=lang)

        # 2. SSML 마크 태그 빌드 (<mark name="chunk_{i}"/>)
        ssml_parts = [f'<speak><prosody rate="{rate_pct}">']
        for c_idx, c in enumerate(scene_chunks):
            c_txt = escape(c["text"].replace("\n", " ").strip())
            ssml_parts.append(f'<mark name="chunk_{c_idx}"/>{c_txt}')
            if c_txt.endswith(('.', '!', '?')):
                ssml_parts.append('<break time="180ms"/>')
            elif c_txt.endswith(','):
                ssml_parts.append('<break time="90ms"/>')
        ssml_parts.append('</prosody></speak>')
        ssml = "".join(ssml_parts)

        # 씬 간 1.2초 대기 버퍼 (Quota 보호)
        if idx > 0:
            time.sleep(1.2)

        print(f"  🎙️ [Scene {s_num}] SSML Timepoint 음성 합성 ({len(scene_chunks)}개 청크): '{script_text[:35]}...'")
        response = synthesize_ssml_with_timepoints(
            client, ssml, voice_name, pitch,
            language_code=language_code, fallback_voice=fallback_voice
        )

        with open(dest_audio, "wb") as f_out:
            f_out.write(response.audio_content)

        dur = get_audio_duration_probe(dest_audio)

        # 3. Google Cloud TTS가 돌려준 실측 타임스탬프 추출
        timepoints = {tp.mark_name: tp.time_seconds for tp in getattr(response, "timepoints", [])}

        aligned_chunks = []
        if timepoints:
            for c_idx, c in enumerate(scene_chunks):
                mark_name = f"chunk_{c_idx}"
                next_mark = f"chunk_{c_idx + 1}"
                st = timepoints.get(mark_name, 0.0)
                if next_mark in timepoints:
                    en = timepoints[next_mark]
                else:
                    en = max(st + 0.5, dur)

                aligned_chunks.append({
                    "text": c["text"],
                    "highlight": c.get("highlight", ""),
                    "start": round(st, 3),
                    "end": round(en, 3)
                })
        else:
            w_timings = calculate_weighted_timings(scene_chunks, dur)
            for c_dict, c_st, c_en in w_timings:
                aligned_chunks.append({
                    "text": c_dict["text"],
                    "highlight": c_dict.get("highlight", ""),
                    "start": round(c_st, 3),
                    "end": round(c_en, 3)
                })

        tp_payload = {
            "scene_number": s_num,
            "duration": dur,
            "timepoints": timepoints,
            "chunks": aligned_chunks
        }

        with open(tp_file_audio, "w", encoding="utf-8") as f_tp:
            json.dump(tp_payload, f_tp, ensure_ascii=False, indent=2)
        with open(tp_file_out, "w", encoding="utf-8") as f_tp:
            json.dump(tp_payload, f_tp, ensure_ascii=False, indent=2)

        # 씬 메타데이터에도 동기화
        sc["chunks"] = aligned_chunks
        print(f"    ✅ [Scene {s_num}] 구글 TTS 실측 Timepoints 저장 완료: {dur:.2f}초 ({len(aligned_chunks)}청크)")

    # 갱신된 청크 정보를 대본 JSON에도 영구 동기화
    script_master_path = os.path.join(out_dir, "masterpiece_script.json")
    if os.path.exists(script_master_path):
        with open(script_master_path, "w", encoding="utf-8") as f_m:
            json.dump(script_data, f_m, ensure_ascii=False, indent=2)

    parent_script_path = os.path.join(os.path.dirname(out_dir), "masterpiece_script.json")
    if os.path.exists(parent_script_path) and os.path.abspath(parent_script_path) != os.path.abspath(script_master_path):
        with open(parent_script_path, "w", encoding="utf-8") as f_p:
            json.dump(script_data, f_p, ensure_ascii=False, indent=2)

    print(f"  🎉 전체 {len(scenes)}씬 Google Cloud Neural2 SSML 음성 및 실측 Timepoints 추출 완료.")
    return audio_dir

if __name__ == "__main__":
    from src.config import get_daily_dir
    target_date = sys.argv[1] if len(sys.argv) > 1 else None
    edition = sys.argv[2] if len(sys.argv) > 2 else "history"

    daily_dir = get_daily_dir(target_date, edition=edition)
    script_path = os.path.join(daily_dir, "masterpiece_script.json")
    if not os.path.exists(script_path):
        daily_dir = get_daily_dir(target_date)
        script_path = os.path.join(daily_dir, "masterpiece_script.json")

    if os.path.exists(script_path):
        with open(script_path, "r", encoding="utf-8") as f:
            script_data = json.load(f)
        generate_scene_audios(script_data, daily_dir, edition=edition)
    else:
        print(f"❌ 대본 파일이 존재하지 않습니다: {script_path}")
