"""history_daily 사운드 이펙트(SFX) 관리 및 합성 모듈 (src/sfx_manager.py).
FFmpeg 내장 lavfi 신시사이저를 활용하여 외부 음원 의존 없이 100% 코드로
로열티 프리 효과음(0초 Impact, 씬 전환 Whoosh, 키워드 Pop)을 자동 생성합니다.
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

# 콘솔 인코딩 방어
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import imageio_ffmpeg
    _sys_ffmpeg = shutil.which("ffmpeg")
    FFMPEG = _sys_ffmpeg if _sys_ffmpeg else imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG = "ffmpeg"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SFX_DIR = os.path.join(BASE_DIR, "assets", "sfx")
os.makedirs(SFX_DIR, exist_ok=True)


def ensure_sfx_assets() -> dict:
    """로열티 프리 합성 SFX(Whoosh, Impact, Pop) 자동 생성 및 무결성 보장."""
    whoosh_file = os.path.join(SFX_DIR, "whoosh.wav")
    impact_file = os.path.join(SFX_DIR, "impact.wav")
    pop_file = os.path.join(SFX_DIR, "pop.wav")

    # 1. Whoosh: 화이트 노이즈 밴드패스(900Hz) 스윕 기반 시네마틱 씬 전환음 (0.4초)
    if not os.path.exists(whoosh_file) or os.path.getsize(whoosh_file) < 1000:
        cmd = [
            FFMPEG, "-y", "-f", "lavfi",
            "-i", "anoisesrc=d=0.4:c=white:r=44100,bandpass=f=900:width_type=q:w=2.2,volume=1.2",
            "-af", "afade=t=in:ss=0:d=0.15,afade=t=out:st=0.2:d=0.2",
            whoosh_file
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
        if res.returncode != 0:
            raise RuntimeError(f"Whoosh SFX 생성 실패: {res.stderr}")
        print(f"  ✨ [SFX 생성] Whoosh 씬 전환음 생성 완료: {whoosh_file}")

    # 2. Impact: 65Hz 서브베이스 드롭 + 딥 베이스 펀치 (오프닝 0초 충격 타격음, 0.6초)
    if not os.path.exists(impact_file) or os.path.getsize(impact_file) < 1000:
        cmd = [
            FFMPEG, "-y", "-f", "lavfi",
            "-i", "sine=f=65:d=0.6:r=44100",
            "-af", "volume=1.4,afade=t=in:ss=0:d=0.03,afade=t=out:st=0.1:d=0.5",
            impact_file
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
        if res.returncode != 0:
            raise RuntimeError(f"Impact SFX 생성 실패: {res.stderr}")
        print(f"  ✨ [SFX 생성] Impact 오프닝 타격음 생성 완료: {impact_file}")

    # 3. Pop: 1200Hz 경쾌한 키워드 팝 톤 (0.12초)
    if not os.path.exists(pop_file) or os.path.getsize(pop_file) < 1000:
        cmd = [
            FFMPEG, "-y", "-f", "lavfi",
            "-i", "sine=f=1200:d=0.12:r=44100",
            "-af", "volume=0.7,afade=t=in:ss=0:d=0.01,afade=t=out:st=0.04:d=0.08",
            pop_file
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
        if res.returncode != 0:
            raise RuntimeError(f"Pop SFX 생성 실패: {res.stderr}")
        print(f"  ✨ [SFX 생성] Pop 키워드 팝음 생성 완료: {pop_file}")

    return {
        "whoosh": whoosh_file,
        "impact": impact_file,
        "pop": pop_file
    }


if __name__ == "__main__":
    print("[SFX Manager] 효과음 에셋 점검 및 생성 시작...")
    sfxs = ensure_sfx_assets()
    print("✅ [SFX Manager] 효과음 라이브러리 검증 완료:")
    for k, v in sfxs.items():
        size_kb = os.path.getsize(v) / 1024
        print(f"   - {k.upper()}: {v} ({size_kb:.1f} KB)")
