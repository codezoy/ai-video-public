"""Motion Mode Router — generation.mode 결정 모듈.

mode 값:
  template   : 기존 template 경로 (기본값)
  ai_motion  : AI Motion Spec JSON 경로 (신규)
  auto       : video_style 기반 자동 선택
    - study   → template
    - youtube → ai_motion

video_defaults.yaml의 generation.mode를 읽고 환경변수 GENERATION_MODE로 오버라이드 가능.
"""
from __future__ import annotations

import logging
import os
from typing import Literal

try:
    from video_defaults import load_video_defaults  # type: ignore[import]
except ImportError:
    from pipelines.video_defaults import load_video_defaults  # type: ignore[no-redef]

log = logging.getLogger(__name__)

GenerationMode = Literal["template", "ai_motion", "auto"]

_VALID_MODES: frozenset[str] = frozenset({"template", "ai_motion", "auto"})

_AUTO_POLICY: dict[str, GenerationMode] = {
    "study": "template",
    "youtube": "ai_motion",
    "lecture": "template",
    "shorts": "template",
}


def _load_config() -> dict:
    return load_video_defaults()


def resolve_mode(video_style: str | None = None) -> GenerationMode:
    """generation.mode를 결정하고 반환한다.

    우선순위:
      1. 환경변수 GENERATION_MODE
      2. config/video_defaults.yaml generation.mode
      3. auto 정책 (video_style 기반)
      4. 기본값 "template"
    """
    env_mode = os.getenv("GENERATION_MODE", "").strip().lower()
    if env_mode in _VALID_MODES:
        log.info("[MOTION_MODE] source=env mode=%s", env_mode)
        return env_mode  # type: ignore[return-value]

    cfg = _load_config()
    cfg_mode = cfg.get("generation", {}).get("mode", "").strip().lower()
    if cfg_mode in _VALID_MODES:
        effective = _apply_auto(cfg_mode, video_style)
        log.info("[MOTION_MODE] source=config raw=%s effective=%s", cfg_mode, effective)
        return effective

    log.info("[MOTION_MODE] source=default mode=template")
    return "template"


def _apply_auto(mode: str, video_style: str | None) -> GenerationMode:
    if mode != "auto":
        return mode  # type: ignore[return-value]
    if video_style:
        style_key = video_style.lower().strip()
        resolved = _AUTO_POLICY.get(style_key, "template")
        log.info("[MOTION_MODE] auto video_style=%s → %s", style_key, resolved)
        return resolved
    log.info("[MOTION_MODE] auto no_style → template")
    return "template"


def is_ai_motion(video_style: str | None = None) -> bool:
    """현재 모드가 ai_motion인지 빠르게 확인한다."""
    return resolve_mode(video_style) == "ai_motion"


def log_mode(video_style: str | None = None) -> str:
    """[MOTION_MODE] 로그 문자열을 반환하고 stdout에 출력한다."""
    mode = resolve_mode(video_style)
    line = f"[MOTION_MODE] mode={mode} video_style={video_style or 'none'}"
    print(line, flush=True)
    return line
