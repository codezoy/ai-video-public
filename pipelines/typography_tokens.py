"""Typography token system — font_registry 기반 4-tier design spec.

Tier    Role(Manifest)  Size(px)  Usage
------  --------------  --------  -----
title   title           72        Scene title, hero headline  (Paperlogy ExtraBold 800)
subtitle section        48        Section header, card label  (Paperlogy Bold 700)
body    body            36        Narration bullets, body copy (Pretendard Regular 400)
caption caption         28        Caption overlay, meta text   (Pretendard SemiBold 600)

폰트 로딩은 font_registry.py에 위임한다. 이 파일에서 직접 font path 관리 금지.
"""
from __future__ import annotations

import logging
from typing import NamedTuple

log = logging.getLogger(__name__)


class TypographyTier(NamedTuple):
    name: str
    font_role: str  # font_manifest.json의 role key
    size: int        # pixel size at 1920x1080
    color: str       # hex color
    line_height: int # px gap between lines


TIERS: dict[str, TypographyTier] = {
    "title":    TypographyTier("title",    "title",   72, "#FFFFFF", 90),
    "subtitle": TypographyTier("subtitle", "section", 48, "#E0E0E0", 62),
    "body":     TypographyTier("body",     "body",    36, "#E0E0E0", 52),
    "caption":  TypographyTier("caption",  "caption", 28, "#B0B0B0", 38),
}

# Canvas constants
CANVAS_W  = 1920
CANVAS_H  = 1080
BG_COLOR  = "#0B0B0B"
ACCENT    = "#FFD966"
PADDING_X = 120
PADDING_Y = 140


def load_font(tier: str, *, size_override: int | None = None):
    """Return a PIL ImageFont for the requested tier via font_registry."""
    import font_registry as _fr

    spec = TIERS.get(tier)
    if spec is None:
        log.warning("Unknown tier %r — using body", tier)
        spec = TIERS["body"]

    size = size_override if size_override is not None else spec.size
    return _fr.load_pil_font(spec.font_role, size)


def resolve_font_path(tier: str) -> str | None:
    """Return the resolved font path for a given tier, or None if unavailable."""
    import font_registry as _fr

    spec = TIERS.get(tier)
    if spec is None:
        return None
    try:
        return str(_fr.resolve_font_path(spec.font_role))
    except RuntimeError:
        return None


def font_info() -> dict[str, str | None]:
    """Return resolved font paths for each tier (useful for dry-run reports)."""
    return {tier: resolve_font_path(tier) for tier in TIERS}
