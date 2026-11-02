import os
import re
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BGM_DIR = os.path.join(BASE_DIR, "assets", "bgm")

# 37곡 고품질 음원의 6대 무드별 라이브러리 풀
MOOD_POOLS = {
    "epic": [
        "bgm_history_epic.mp3",
        "impact_prelude.mp3",
        "five_armies.mp3",
        "call_to_adventure.mp3",
        "devastation_and_revenge.mp3",
        "clash_defiant.mp3",
        "stormfront.mp3",
        "final_battle_of_the_dark_wizards.mp3"
    ],
    "triumphant": [
        "despair_and_triumph.mp3",
        "reign_supreme.mp3",
        "aces_high.mp3"
    ],
    "dramatic": [
        "hero_down.mp3",
        "killers.mp3",
        "minima.mp3",
        "night_of_chaos.mp3",
        "the_descent.mp3",
        "wounded.mp3"
    ],
    "mystery": [
        "this_house.mp3",
        "ghost_story.mp3",
        "unanswered_questions.mp3",
        "darkling.mp3",
        "division.mp3",
        "ancient_rite.mp3",
        "achaidh_cheide.mp3"
    ],
    "suspense": [
        "darkness_is_coming.mp3",
        "hidden_agenda.mp3",
        "interloper.mp3",
        "gathering_darkness.mp3",
        "volatile_reaction.mp3",
        "impending_boom.mp3",
        "oppressive_gloom.mp3"
    ],
    "somber": [
        "cryptic_sorrow.mp3",
        "heartbreaking.mp3",
        "at_rest.mp3",
        "night_vigil.mp3",
        "constance.mp3",
        "anguish.mp3"
    ]
}


def select_rotated_bgm(chosen_bgm_or_mood: str, date_str: str = None) -> str:
    """선택된 BGM 또는 무드를 기반으로, 날짜에 따라 같은 무드 내의 음원을 골고루 순환(Round-Robin) 선택"""
    chosen = (chosen_bgm_or_mood or "").strip()

    # 1. 대상 무드 매칭
    matched_mood = "epic"
    for mood, pool in MOOD_POOLS.items():
        if chosen.lower() == mood:
            matched_mood = mood
            break
        if chosen in pool:
            matched_mood = mood
            break

    # 키워드 기반 추가 추론
    if matched_mood == "epic" and chosen not in MOOD_POOLS["epic"]:
        c_low = chosen.lower()
        if any(k in c_low for k in ["mystery", "house", "ghost", "ancient"]):
            matched_mood = "mystery"
        elif any(k in c_low for k in ["dark", "agenda", "interloper", "suspense"]):
            matched_mood = "suspense"
        elif any(k in c_low for k in ["sorrow", "heart", "rest", "vigil", "anguish", "somber"]):
            matched_mood = "somber"
        elif any(k in c_low for k in ["triumph", "reign", "aces"]):
            matched_mood = "triumphant"
        elif any(k in c_low for k in ["hero", "chaos", "descent", "killer"]):
            matched_mood = "dramatic"

    # 2. 날짜 기반 시드 산출
    seed = 0
    if date_str:
        digits = re.sub(r"\D", "", date_str)
        if len(digits) >= 8:
            m = int(digits[4:6])
            d = int(digits[6:8])
            seed = m * 31 + d
        elif len(digits) >= 2:
            seed = int(digits)
    if seed == 0:
        now = datetime.now()
        seed = now.month * 31 + now.day

    # 3. 풀 내에서 순환 선택
    pool = MOOD_POOLS[matched_mood]
    rot_idx = seed % len(pool)
    selected_file = pool[rot_idx]

    # 4. 파일 존재 여부 검증
    full_path = os.path.join(BGM_DIR, selected_file)
    if not os.path.exists(full_path):
        # 존재하는 첫 번째 파일 폴백
        for f in pool:
            if os.path.exists(os.path.join(BGM_DIR, f)):
                return f
        return "bgm_history_epic.mp3"

    return selected_file

