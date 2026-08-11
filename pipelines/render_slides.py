# DEPRECATED: 2026-05-30 — 표준 경로는 scene_render.py 사용. REMOVAL_CANDIDATE: 2026-06-30
"""S5 slide renderer — scenes.json → work/slides/sceneNN.png.

Produces 1920x1080 static PNG slides for each scene.
Uses the 4-tier Pretendard typography system from typography_tokens.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

try:
    from rich.console import Console
    _console = Console(stderr=True)

    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "cyan", "warning": "yellow", "error": "red",
                 "success": "green"}.get(level, "white")
        _console.print(f"[{color}][render_slides][/{color}] {msg}")
except ImportError:
    logging.basicConfig(level=logging.INFO)
    _logger = logging.getLogger("render_slides")

    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logger, level, _logger.info)(f"[render_slides] {msg}")

_PROJECT_ROOT = Path(__file__).parent.parent
_WORK_DIR     = _PROJECT_ROOT / "work"


# ── Canvas constants (imported from tokens for consistency) ──────────────────

_W, _H     = 1920, 1080
_BG        = "#0B0B0B"
_ACCENT    = "#FFD966"
_PAD_X     = 120
_PAD_Y_TOP = 140


def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _wrap_text(text: str, font, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    from PIL import ImageDraw, Image
    dummy = Image.new("RGB", (1, 1))
    draw  = ImageDraw.Draw(dummy)
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def render_scene_png(
    scene: dict,
    output_path: Path,
    *,
    force: bool = False,
) -> Path:
    """Render one scene to a 1920x1080 PNG using Pretendard typography."""
    from PIL import Image, ImageDraw

    if output_path.exists() and not force:
        _log(f"skip (exists): {output_path.name}", "warning")
        return output_path

    # ── Import tokens ──────────────────────────────────────────────────────
    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)
    from typography_tokens import load_font, TIERS, ACCENT, PADDING_X, PADDING_Y

    # ── Create canvas ──────────────────────────────────────────────────────
    img  = Image.new("RGB", (_W, _H), _hex_rgb(_BG))
    draw = ImageDraw.Draw(img)

    template = (scene.get("template_type") or "flow_steps")
    title    = scene.get("title", "")
    narration = scene.get("narration", "")
    visual_data = scene.get("visual_data") or {}

    # visual_data structured items (preferred) → bullets fallback
    raw_items: list[Any] = []
    for key in ("steps", "keywords", "nodes", "events", "takeaways"):
        candidate = visual_data.get(key)
        if candidate and isinstance(candidate, list):
            raw_items = candidate
            break
    if not raw_items:
        raw_items = scene.get("bullets") or []

    bullets: list[str] = []
    for b in raw_items:
        if isinstance(b, dict):
            bullets.append(b.get("text", ""))
        else:
            bullets.append(str(b))

    font_title   = load_font("title")
    font_subtitle = load_font("subtitle")
    font_body    = load_font("body")
    max_text_w   = _W - PADDING_X * 2

    y = PADDING_Y

    # ── Accent bar ─────────────────────────────────────────────────────────
    draw.rectangle([PADDING_X - 14, y, PADDING_X - 6, y + TIERS["title"].size + 8],
                   fill=_hex_rgb(ACCENT))

    # ── Title ──────────────────────────────────────────────────────────────
    if title:
        lines = _wrap_text(title, font_title, max_text_w)
        for line in lines:
            draw.text((PADDING_X, y), line, font=font_title,
                      fill=_hex_rgb(TIERS["title"].color))
            y += TIERS["title"].line_height
        y += 20  # gap after title

    # ── Bullets / body ─────────────────────────────────────────────────────
    if bullets:
        for bullet in bullets:
            lines = _wrap_text(bullet, font_body, max_text_w - 40)
            for i, line in enumerate(lines):
                prefix = "• " if i == 0 else "  "
                draw.text((PADDING_X, y), prefix + line, font=font_body,
                          fill=_hex_rgb(TIERS["body"].color))
                y += TIERS["body"].line_height
        y += 16
    elif narration and template not in ("hero_title", "TITLE_OPEN"):
        # fallback: show first 150 chars of narration as subtitle
        snippet = narration[:150]
        lines = _wrap_text(snippet, font_subtitle, max_text_w)
        for line in lines[:4]:
            draw.text((PADDING_X, y), line, font=font_subtitle,
                      fill=_hex_rgb(TIERS["subtitle"].color))
            y += TIERS["subtitle"].line_height

    # ── Scene index watermark (bottom-right) ──────────────────────────────
    font_caption = load_font("caption")
    idx_text = f"#{scene.get('id', 0)}"
    draw.text((_W - PADDING_X, _H - 60), idx_text, font=font_caption,
              fill=_hex_rgb(TIERS["caption"].color), anchor="rs")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    return output_path


def render_slides(
    scenes_json: Path,
    slides_dir: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> list[Path]:
    """S5: render all scenes from scenes.json to PNG slides."""
    if not scenes_json.exists():
        _log(f"scenes.json not found: {scenes_json}", "error")
        sys.exit(1)

    data   = json.loads(scenes_json.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])

    if dry_run:
        _log(f"dry-run: would render {len(scenes)} slides → {slides_dir}")
        # validate font availability
        pipelines_dir = str(Path(__file__).parent)
        if pipelines_dir not in sys.path:
            sys.path.insert(0, pipelines_dir)
        from typography_tokens import font_info
        info = font_info()
        for tier, path in info.items():
            status = path if path else "NOT FOUND (will use PIL default)"
            _log(f"  font[{tier}]: {status}")
        return []

    slides_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[Path] = []
    for scene in scenes:
        sid = scene.get("id", 0)
        out = slides_dir / f"scene{sid:02d}.png"
        render_scene_png(scene, out, force=force)
        _log(f"scene{sid:02d}.png OK")
        rendered.append(out)

    _log(f"render_slides done — {len(rendered)} PNGs in {slides_dir}", "success")
    return rendered


# ── CLI entry ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="S5 slide renderer")
    parser.add_argument("--scenes-json", type=Path,
                        default=_WORK_DIR / "latest" / "scenes.json")
    parser.add_argument("--slides-dir", type=Path,
                        default=_WORK_DIR / "latest" / "slides")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    render_slides(
        args.scenes_json,
        args.slides_dir,
        force=args.force,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
