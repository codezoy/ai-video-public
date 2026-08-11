"""S6.5 애니메이션 슬라이드 — 불릿 페이드인 + TTS 싱크 씬 합성.

의존성: moviepy==1.0.3, Pillow
설치: pip install moviepy==1.0.3 Pillow
참조: 플레이북 v2 섹션 2.5(애니메이션 전략), 6.5(애니메이션 컴포지션)
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import TypedDict

try:
    from rich.console import Console
    _console = Console(stderr=True)
    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "green", "warning": "yellow", "error": "red"}.get(level, "white")
        _console.print(f"[{color}][render_animated][/{color}] {msg}")
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[render_animated] {msg}")

# ── 상수 ─────────────────────────────────────────────────────────────────────
_CANVAS_W  = 1920
_CANVAS_H  = 1080
_BG_COLOR  = "#0B0B0B"
_FPS       = 30

_TEXT_COLOR     = "#E0E0E0"
_EMPHASIS_COLOR = "#FFD966"
_BULLET_SIZE    = 52
_LEADING        = 80    # 줄 높이 (폰트 + 행간)
_PADDING_X      = 120
_PADDING_Y      = 140

class BulletDict(TypedDict):
    text: str
    emphasis: list[str]
    appear_at_ms: int


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _load_font(size: int, bold: bool = False):
    """font_registry를 통해 폰트를 로드한다.
    bold=True → Paperlogy Bold(section role), bold=False → Pretendard Regular(body role).
    """
    import font_registry as _fr
    role = "section" if bold else "body"
    return _fr.load_pil_font(role, size)


def _render_bullet_row(
    draw,
    text: str,
    emphasis_words: list[str],
    x: int,
    y: int,
    font_regular,
    font_bold,
    text_rgb: tuple[int, int, int],
    emph_rgb: tuple[int, int, int],
) -> None:
    """단어 단위로 색상을 구분해 한 줄 불릿을 그린다."""
    words = text.split()
    cursor_x = x

    # 불릿 마커 먼저 그리기
    marker = "• "
    m_bbox = font_regular.getbbox(marker)
    draw.text((cursor_x, y), marker, font=font_regular, fill=emph_rgb)
    cursor_x += (m_bbox[2] - m_bbox[0]) if m_bbox else 20

    for i, word in enumerate(words):
        is_emphasis = word in emphasis_words or word.rstrip(",.;:!?") in emphasis_words
        font = font_bold if is_emphasis else font_regular
        color = emph_rgb if is_emphasis else text_rgb

        # 단어 + 공백(마지막 제외)
        display = word if i == len(words) - 1 else word + " "
        w_bbox = font.getbbox(display)
        draw.text((cursor_x, y), display, font=font, fill=color)
        cursor_x += (w_bbox[2] - w_bbox[0]) if w_bbox else len(display) * 20


def render_bullet_frame(
    bullets: list[BulletDict],
    visible_until_idx: int,
    out_path: Path,
) -> Path:
    """불릿 프레임 PNG를 생성한다.

    Args:
        bullets: 불릿 목록. 각 항목은 text/emphasis/appear_at_ms 포함.
        visible_until_idx: 이 인덱스까지의 불릿만 렌더 (나머지는 투명).
        out_path: 출력 PNG 경로.

    Returns:
        생성된 PNG 경로.
    """
    from PIL import Image, ImageDraw

    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    bg_rgb   = _hex_to_rgb(_BG_COLOR)
    txt_rgb  = _hex_to_rgb(_TEXT_COLOR)
    emph_rgb = _hex_to_rgb(_EMPHASIS_COLOR)

    canvas = Image.new("RGB", (_CANVAS_W, _CANVAS_H), bg_rgb)
    draw   = ImageDraw.Draw(canvas)

    font_regular = _load_font(_BULLET_SIZE)
    font_bold    = _load_font(_BULLET_SIZE, bold=True)

    y = _PADDING_Y
    for idx, bullet in enumerate(bullets):
        if idx > visible_until_idx:
            break
        _render_bullet_row(
            draw,
            text=bullet["text"],
            emphasis_words=bullet.get("emphasis", []),
            x=_PADDING_X,
            y=y,
            font_regular=font_regular,
            font_bold=font_bold,
            text_rgb=txt_rgb,
            emph_rgb=emph_rgb,
        )
        y += _LEADING

    canvas.save(str(out_path), "PNG")
    return out_path


def compose_scene_with_timing(
    scene: dict,
    tts_wav_path: Path,
    out_path: Path,
) -> Path:
    """불릿 프레임들을 시간축에 배치하고 TTS 오디오와 합성해 씬 MP4를 생성한다.

    Args:
        scene: scenes.json 의 단일 씬 dict.
            bullets 필드는 BulletDict 목록 (appear_at_ms 포함 필수).
        tts_wav_path: TTS 음성 파일 경로 (.mp3/.wav).
        out_path: 출력 MP4 경로.

    Returns:
        생성된 씬 MP4 경로.
    """
    try:
        from moviepy.editor import (
            AudioFileClip,
            CompositeVideoClip,
            ImageClip,
        )
    except ImportError:
        raise ImportError(
            "moviepy 가 설치되지 않았습니다.\n"
            "설치: pip install moviepy==1.0.3"
        )
    from PIL import Image

    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    bullets: list[BulletDict] = scene.get("bullets", [])

    # bullets 가 문자열 배열(구형 스키마)이면 변환
    normalized: list[BulletDict] = []
    for i, b in enumerate(bullets):
        if isinstance(b, str):
            normalized.append({
                "text": b,
                "emphasis": [],
                "appear_at_ms": i * 3000,
            })
        else:
            normalized.append(b)

    # 오디오 길이 계산
    audio_clip = AudioFileClip(str(tts_wav_path))
    audio_duration = audio_clip.duration

    # 씬 길이 = max(마지막 불릿 등장 + 3초, 오디오 길이)
    last_ms = max((b["appear_at_ms"] for b in normalized), default=0)
    scene_duration = max(last_ms / 1000 + 3.0, audio_duration)

    _log(f"씬 길이: {scene_duration:.2f}s (오디오: {audio_duration:.2f}s)")

    # 임시 디렉토리에 불릿 프레임 PNG 생성
    clips: list = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        for i in range(len(normalized)):
            frame_path = tmp / f"bullet_frame_{i:02d}.png"
            render_bullet_frame(normalized, visible_until_idx=i, out_path=frame_path)

            appear_sec = normalized[i]["appear_at_ms"] / 1000.0

            # 각 프레임은 등장 시점부터 씬 끝까지 유지된다.
            # 이후 프레임이 CompositeVideoClip 에서 위에 쌓이므로
            # "이전 불릿 유지 + 새 불릿 fade-in" 효과가 정확히 구현된다.
            # (이전 방식인 end_sec-appear_sec 는 직전 불릿이 순간 사라지는 flash 버그 발생)
            duration = max(scene_duration - appear_sec, 0.1)

            clip = (
                ImageClip(str(frame_path))
                .set_start(appear_sec)
                .set_duration(duration)
                .crossfadein(0.3)
            )
            clips.append(clip)

        if not clips:
            # 불릿 없으면 빈 배경 프레임
            blank_path = tmp / "blank.png"
            from PIL import Image as _Img
            _Img.new("RGB", (_CANVAS_W, _CANVAS_H), _hex_to_rgb(_BG_COLOR)).save(str(blank_path))
            clips = [ImageClip(str(blank_path)).set_duration(scene_duration)]

        composite = CompositeVideoClip(clips, size=(_CANVAS_W, _CANVAS_H))
        composite = composite.set_duration(scene_duration).set_audio(
            audio_clip.set_duration(min(audio_duration, scene_duration))
        )

        composite.write_videofile(
            str(out_path),
            fps=_FPS,
            codec="libx264",
            audio_codec="aac",
            verbose=False,
            logger=None,
        )

    audio_clip.close()
    _log(f"씬 저장 완료: {out_path}")
    return out_path


if __name__ == "__main__":
    import argparse
    import json

    p = argparse.ArgumentParser(description="애니메이션 슬라이드 테스트 렌더.")
    sub = p.add_subparsers(dest="cmd")

    # 정지 프레임 테스트
    pf = sub.add_parser("frame", help="불릿 프레임 PNG 렌더")
    pf.add_argument("--out", required=True)
    pf.add_argument("--idx", type=int, default=0)

    # 씬 합성 테스트
    ps = sub.add_parser("scene", help="씬 MP4 합성")
    ps.add_argument("--scene-json", required=True, help="씬 dict JSON 문자열 또는 파일 경로")
    ps.add_argument("--audio", required=True, help="TTS 음성 파일 경로")
    ps.add_argument("--out", required=True)

    args = p.parse_args()

    if args.cmd == "frame":
        sample_bullets: list[BulletDict] = [
            {"text": "Claude Code는 로컬 CLI 에이전트다", "emphasis": ["Claude Code", "로컬 CLI"], "appear_at_ms": 0},
            {"text": "비용은 40% 절감 가능하다", "emphasis": ["40%", "절감"], "appear_at_ms": 3000},
            {"text": "핵심은 LLM Router 설계다", "emphasis": ["핵심은", "LLM Router"], "appear_at_ms": 6000},
        ]
        render_bullet_frame(sample_bullets, visible_until_idx=args.idx, out_path=Path(args.out))
        print(f"프레임 저장: {args.out}")

    elif args.cmd == "scene":
        scene_data = args.scene_json
        if Path(scene_data).exists():
            scene_dict = json.loads(Path(scene_data).read_text())
        else:
            scene_dict = json.loads(scene_data)
        compose_scene_with_timing(scene_dict, Path(args.audio), Path(args.out))
        print(f"씬 저장: {args.out}")

    else:
        p.print_help()
