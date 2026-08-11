"""Generate a fallback slide PNG when normal rendering fails.

Design spec:
- Dark navy (#0D1B2A) to steel blue (#1E3A5F) vertical gradient — NEVER solid black.
- Semi-transparent title card + bullet card overlays.
- Accent left bar (#5B8DB8) beside title.
- Caption safe area at bottom with scene index.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

_W, _H = 1920, 1080

_NAVY = (13, 27, 42)       # #0D1B2A
_STEEL = (30, 58, 95)      # #1E3A5F
_ACCENT = (91, 141, 184)   # #5B8DB8
_TEXT_PRIMARY = (232, 232, 232)
_TEXT_SECONDARY = (180, 196, 210)

def _load_font(size: int, role: str = "body") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """font_registry를 통해 폰트를 로드한다. 실패 시 시스템 기본 폰트로 폴백."""
    import sys as _sys
    _pipelines_dir = str(Path(__file__).parent)
    if _pipelines_dir not in _sys.path:
        _sys.path.insert(0, _pipelines_dir)
    try:
        import font_registry as _fr
        return _fr.load_pil_font(role, size)
    except Exception as exc:
        log.error("font_registry 로드 실패(role=%s, size=%d): %s — 기본 폰트 사용", role, size, exc)
        return ImageFont.load_default()


def _make_gradient() -> Image.Image:
    """Create dark navy→steel blue vertical gradient."""
    arr = np.zeros((_H, _W, 3), dtype=np.uint8)
    for row in range(_H):
        t = row / (_H - 1)
        arr[row, :, 0] = round(_NAVY[0] + (_STEEL[0] - _NAVY[0]) * t)
        arr[row, :, 1] = round(_NAVY[1] + (_STEEL[1] - _NAVY[1]) * t)
        arr[row, :, 2] = round(_NAVY[2] + (_STEEL[2] - _NAVY[2]) * t)
    return Image.fromarray(arr, "RGB")


def _overlay_rect(base: Image.Image, x: int, y: int, w: int, h: int, color: tuple, alpha: int) -> None:
    """Draw a semi-transparent rectangle onto base (RGBA composite)."""
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle([x, y, x + w, y + h], fill=(*color, alpha))
    base.paste(Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB"), (0, 0))


def generate(scene: dict[str, Any], output_path: Path | str, *, scene_index: int = 0) -> Path:
    """Render a fallback slide PNG for scene.

    Args:
        scene: scene dict with keys 'title', 'narration', 'bullets', etc.
        output_path: where to write the PNG.
        scene_index: 1-based scene number for caption.

    Returns:
        Resolved Path to the written PNG.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    title: str = scene.get("title") or scene.get("heading") or f"Scene {scene_index}"
    bullets_raw = scene.get("bullets") or scene.get("points") or []
    if isinstance(bullets_raw, str):
        bullets_raw = [b.strip() for b in bullets_raw.splitlines() if b.strip()]
    bullets: list[str] = bullets_raw[:5]  # max 5

    # --- Gradient background ---
    img = _make_gradient()
    draw = ImageDraw.Draw(img)

    # --- Title card overlay (top 45%) ---
    card_x, card_y = 120, 160
    card_w, card_h = 1680, 320
    _overlay_rect(img, card_x, card_y, card_w, card_h, (255, 255, 255), 18)
    draw = ImageDraw.Draw(img)

    # Accent left bar
    draw.rectangle(
        [card_x, card_y, card_x + 8, card_y + card_h],
        fill=_ACCENT,
    )

    # Title text
    font_title = _load_font(72, role="title")
    draw.text(
        (card_x + 40, card_y + 40),
        title,
        font=font_title,
        fill=_TEXT_PRIMARY,
    )

    # Chip / accent label
    chip_text = "FALLBACK"
    font_chip = _load_font(28, role="caption")
    chip_bbox = draw.textbbox((0, 0), chip_text, font=font_chip)
    chip_w = chip_bbox[2] - chip_bbox[0] + 24
    chip_x = card_x + 40
    chip_y = card_y + 200
    draw.rounded_rectangle(
        [chip_x, chip_y, chip_x + chip_w, chip_y + 44],
        radius=8,
        fill=(*_ACCENT, 180),
    )
    draw.text((chip_x + 12, chip_y + 8), chip_text, font=font_chip, fill=(255, 255, 255))

    # --- Bullet card overlay (middle area) ---
    if bullets:
        bcard_x, bcard_y = 120, 520
        bcard_w, bcard_h = 1680, min(60 + len(bullets) * 76, 440)
        _overlay_rect(img, bcard_x, bcard_y, bcard_w, bcard_h, (255, 255, 255), 12)
        draw = ImageDraw.Draw(img)

        font_bullet = _load_font(44, role="body")
        by = bcard_y + 28
        for bullet in bullets:
            # bullet dot
            draw.ellipse([bcard_x + 32, by + 12, bcard_x + 52, by + 32], fill=_ACCENT)
            draw.text(
                (bcard_x + 72, by),
                bullet[:80],
                font=font_bullet,
                fill=_TEXT_SECONDARY,
            )
            by += 76

    # --- Caption safe area (bottom) ---
    font_caption = _load_font(32, role="caption")
    caption = f"Scene {scene_index:02d}  |  Rendering failed — fallback slide"
    draw.text(
        (_W // 2, _H - 60),
        caption,
        font=font_caption,
        fill=(140, 160, 180),
        anchor="mm",
    )

    img.save(str(output_path), "PNG")
    log.info("Fallback slide written: %s", output_path)
    return output_path
