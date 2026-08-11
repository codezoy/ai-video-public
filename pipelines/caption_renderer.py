# =============================================================================
# DEPRECATED — Python Caption Renderer
# -----------------------------------------------------------------------------
# 이 모듈은 Remotion CaptionOverlay로 대체되었습니다.
# (hyperframe/src/components/CaptionOverlay.tsx)
#
# 기본 파이프라인에서는 호출되지 않습니다.
# legacy 모드: 환경변수 LEGACY_CAPTION_OVERLAY=true 로만 활성화 가능.
#
# 즉시 삭제 금지 — legacy 재현 및 롤백 용도로 보존.
# =============================================================================

"""caption_renderer.py — PIL 기반 캡션 이미지 생성 (MoviePy overlay용).

캡션 스타일 규격:
- font: Pretendard SemiBold (weight=600)
- font_size: 56~64px (길이에 따라 조정)
- color: white, stroke: black 4px
- background: rgba(0,0,0,0.55), radius: 12px, padding: 16px
- 위치: 하단 중앙, bottom safe area = 80px
- 최대 2줄, 자동 줄바꿈
"""

from __future__ import annotations

import logging
import textwrap

import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ── 스타일 상수 ──────────────────────────────────────────────────────────────
FONT_SIZE_DEFAULT = 60
FONT_SIZE_LONG = 52        # 긴 텍스트(20자 초과)
FONT_SIZE_VLONG = 46       # 매우 긴 텍스트(30자 초과)
MAX_CHARS_PER_LINE = 22    # 1줄 최대 글자 수 (Shorts 기준)
MAX_LINES = 2
TEXT_COLOR = (255, 255, 255, 255)       # 흰색
STROKE_COLOR = (0, 0, 0, 255)          # 검정
STROKE_WIDTH = 4
BG_COLOR = (0, 0, 0, 140)              # rgba(0,0,0,0.55) ≈ alpha=140
PADDING_X = 24
PADDING_Y = 16
CORNER_RADIUS = 12
SAFE_AREA_BOTTOM = 80       # px (1080p 기준)

def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """font_registry를 통해 caption role 폰트(Pretendard SemiBold)를 로드한다."""
    import font_registry as _fr
    font = _fr.load_pil_font("caption", size)
    # CAPTION_GLYPH_AUDIT: 실제 렌더 직전 font 정보 출력
    spec = _fr.get_font_spec("caption")
    font_path = _fr.resolve_font_path("caption")
    logger.info(
        "[CAPTION_GLYPH_AUDIT] font_role=caption font_path=%s family=%s weight=%s variation=%s font_size=%d",
        font_path, spec.get("family"), spec.get("weight"), spec.get("variation_name"), size,
    )
    return font


def _wrap_text(text: str, max_chars: int) -> list[str]:
    """텍스트를 max_chars 기준으로 줄바꿈. 최대 MAX_LINES줄."""
    text = text.strip()
    if not text:
        return []

    # 이미 짧으면 단일 줄
    if len(text) <= max_chars:
        return [text]

    # textwrap (한국어는 글자 단위로 거의 동작)
    # 공백 기준 우선, 없으면 글자 수 기준 강제
    if " " in text:
        lines = textwrap.wrap(text, width=max_chars, break_long_words=True, break_on_hyphens=False)
    else:
        # 한국어: 글자 수 기준으로 나누기
        lines = [text[i : i + max_chars] for i in range(0, len(text), max_chars)]

    return lines[:MAX_LINES]


def _rounded_rectangle(draw: ImageDraw.ImageDraw, xy, radius: int, fill) -> None:
    """둥근 모서리 사각형 그리기."""
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.ellipse([x0, y0, x0 + 2 * radius, y0 + 2 * radius], fill=fill)
    draw.ellipse([x1 - 2 * radius, y0, x1, y0 + 2 * radius], fill=fill)
    draw.ellipse([x0, y1 - 2 * radius, x0 + 2 * radius, y1], fill=fill)
    draw.ellipse([x1 - 2 * radius, y1 - 2 * radius, x1, y1], fill=fill)


def render_caption_frame(
    text: str,
    canvas_w: int,
    canvas_h: int,
) -> np.ndarray:
    """캡션 텍스트를 포함한 RGBA 이미지를 numpy array로 반환.

    반환값: shape=(canvas_h, canvas_w, 4), dtype=uint8 (RGBA)
    """
    if not text or not text.strip():
        return np.zeros((canvas_h, canvas_w, 4), dtype=np.uint8)

    # 길이에 따른 폰트 크기 조정
    text_len = len(text)
    if text_len > 30:
        font_size = FONT_SIZE_VLONG
        max_chars = 28
    elif text_len > 20:
        font_size = FONT_SIZE_LONG
        max_chars = 24
    else:
        font_size = FONT_SIZE_DEFAULT
        max_chars = MAX_CHARS_PER_LINE

    font = _load_font(font_size)
    lines = _wrap_text(text, max_chars)
    if not lines:
        return np.zeros((canvas_h, canvas_w, 4), dtype=np.uint8)

    # 텍스트 크기 측정
    dummy_img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    dummy_draw = ImageDraw.Draw(dummy_img)
    line_bboxes = [dummy_draw.textbbox((0, 0), ln, font=font, stroke_width=STROKE_WIDTH) for ln in lines]
    line_heights = [bb[3] - bb[1] for bb in line_bboxes]
    line_widths = [bb[2] - bb[0] for bb in line_bboxes]

    line_gap = 8
    total_text_h = sum(line_heights) + line_gap * (len(lines) - 1)
    max_text_w = max(line_widths) if line_widths else 0

    box_w = max_text_w + PADDING_X * 2
    box_h = total_text_h + PADDING_Y * 2

    # 중앙 하단 위치
    box_x0 = (canvas_w - box_w) // 2
    box_y1 = canvas_h - SAFE_AREA_BOTTOM
    box_y0 = box_y1 - box_h
    box_x1 = box_x0 + box_w

    # 캔버스 생성 (완전 투명)
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    # 반투명 배경 레이어
    bg_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg_layer)
    _rounded_rectangle(bg_draw, (box_x0, box_y0, box_x1, box_y1), CORNER_RADIUS, BG_COLOR)
    canvas = Image.alpha_composite(canvas, bg_layer)

    # 텍스트 렌더링
    text_draw = ImageDraw.Draw(canvas)
    cursor_y = box_y0 + PADDING_Y
    for i, line in enumerate(lines):
        bb = line_bboxes[i]
        lw = line_widths[i]
        text_x = box_x0 + PADDING_X + (max_text_w - lw) // 2 - bb[0]
        text_y = cursor_y - bb[1]

        # stroke (검정)
        text_draw.text(
            (text_x, text_y),
            line,
            font=font,
            fill=STROKE_COLOR,
            stroke_width=STROKE_WIDTH,
            stroke_fill=STROKE_COLOR,
        )
        # 흰색 텍스트
        text_draw.text(
            (text_x, text_y),
            line,
            font=font,
            fill=TEXT_COLOR,
        )
        cursor_y += line_heights[i] + line_gap

    return np.array(canvas)


def make_caption_clips(
    caption_segments: list[dict],
    canvas_w: int,
    canvas_h: int,
    scene_duration: float,
) -> list:
    """caption_segments → MoviePy ImageClip 리스트.

    MoviePy는 RGBA 배열의 alpha를 자동으로 mask로 처리하지 않는다.
    RGB와 alpha(mask)를 분리해서 set_mask()로 명시적으로 지정해야
    슬라이드 위에 자막만 투명하게 올라간다.

    Args:
        caption_segments: [{"start_ms": int, "end_ms": int, "text": str}, ...]
        canvas_w / canvas_h: 영상 해상도
        scene_duration: 씬 전체 길이(초)

    Returns:
        list of moviepy ImageClip (mask 적용, 배경 투명)
    """
    from moviepy.editor import ImageClip

    clips = []
    for seg in caption_segments:
        start_sec = seg["start_ms"] / 1000.0
        end_sec = min(seg["end_ms"] / 1000.0, scene_duration)
        duration = end_sec - start_sec
        if duration <= 0:
            continue

        rgba = render_caption_frame(seg["text"], canvas_w, canvas_h)
        rgb = rgba[:, :, :3]
        alpha = rgba[:, :, 3].astype(float) / 255.0  # [0,1] float

        mask_clip = ImageClip(alpha, ismask=True).set_duration(duration)
        clip = (
            ImageClip(rgb, ismask=False)
            .set_mask(mask_clip)
            .set_start(start_sec)
            .set_duration(duration)
        )
        clips.append(clip)

    return clips
