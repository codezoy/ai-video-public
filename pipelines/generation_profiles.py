"""Generation Profile — target_duration_sec → profile 자동 선택.

profile은 scene budget / narration budget / critique policy를 통합 관리한다.
SaaS 확장 시 사용자 선택 가능하도록 dict 형태로 관리한다.
"""
from __future__ import annotations

from typing import Any

GENERATION_PROFILES: dict[str, dict[str, Any]] = {
    "SHORTS": {
        "max_duration_sec": 60,
        "min_scenes": 3,
        "max_scenes": 5,  # legacy: not used in scene-first path (direct_scene_gen.py bypasses this)
        "max_scene_narration_chars": 180,
        "max_total_narration_chars": 900,
        "critique_max_runs": 1,
        "regen_max_runs": 1,
        "writer_high_enabled": False,
        "multi_judge_enabled": False,
        "fast_path": True,
    },
    "MICRO_LECTURE": {
        "max_duration_sec": 180,
        "min_scenes": 5,
        "max_scenes": 8,  # legacy: not used in scene-first path (direct_scene_gen.py bypasses this)
        "max_scene_narration_chars": 260,
        "max_total_narration_chars": 1800,
        "critique_max_runs": 1,
        "regen_max_runs": 1,
        "writer_high_enabled": False,
        "multi_judge_enabled": False,
        "fast_path": True,
    },
    "LECTURE": {
        "max_duration_sec": 600,
        "min_scenes": 8,
        "max_scenes": 15,  # legacy: not used in scene-first path (direct_scene_gen.py bypasses this)
        "max_scene_narration_chars": 400,
        "max_total_narration_chars": 5000,
        "critique_max_runs": 2,
        "regen_max_runs": 2,
        "writer_high_enabled": True,
        "multi_judge_enabled": True,
        "fast_path": True,
    },
    "LONG_LECTURE": {
        "max_duration_sec": 99999,
        "min_scenes": 15,
        "max_scenes": 40,  # legacy: not used in scene-first path (direct_scene_gen.py bypasses this)
        "max_scene_narration_chars": 500,
        "max_total_narration_chars": 15000,
        "critique_max_runs": 3,
        "regen_max_runs": 3,
        "writer_high_enabled": True,
        "multi_judge_enabled": True,
        "fast_path": True,
    },
}

_PROFILE_ORDER = ["SHORTS", "MICRO_LECTURE", "LECTURE", "LONG_LECTURE"]


def select_profile(target_duration_sec: int) -> tuple[str, dict[str, Any]]:
    """target_duration_sec → (profile_name, profile_config) 반환."""
    for name in _PROFILE_ORDER:
        cfg = GENERATION_PROFILES[name]
        if target_duration_sec <= cfg["max_duration_sec"]:
            if cfg.get("fast_path") is not True:
                raise RuntimeError(
                    "LONG_PATH has been removed. FAST_PATH is the only supported generation path."
                )
            return name, cfg
    name = "LONG_LECTURE"
    if GENERATION_PROFILES[name].get("fast_path") is not True:
        raise RuntimeError(
            "LONG_PATH has been removed. FAST_PATH is the only supported generation path."
        )
    return name, GENERATION_PROFILES[name]


def log_profile(target_duration_sec: int) -> str:
    """[GEN_PROFILE] 로그 문자열 반환."""
    name, cfg = select_profile(target_duration_sec)
    return (
        f"[GEN_PROFILE] target_duration={target_duration_sec}"
        f" profile={name}"
        f" min_scenes={cfg['min_scenes']}"
        f" max_scenes={cfg['max_scenes']}"
        f" max_scene_chars={cfg['max_scene_narration_chars']}"
        f" max_total_chars={cfg['max_total_narration_chars']}"
        f" critique_max={cfg['critique_max_runs']}"
        f" regen_max={cfg['regen_max_runs']}"
    )
