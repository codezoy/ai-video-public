# DEPRECATED: 2026-05-30 — 표준 경로에서 미호출. REMOVAL_CANDIDATE: 2026-06-30
"""S6 시각 자산 — 하이라이트 카드(정의/사례/주의)를 Pillow로 렌더링한다.

의존성: Pillow
설치: pip install Pillow
참조: 플레이북 v2 섹션 2(시각 전략), 섹션 6.4(슬라이드·다이어그램·코드 공존 규칙)
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal

CardKind = Literal["def", "case", "warn"]

try:
    from rich.console import Console
    _console = Console(stderr=True)
    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "green", "warning": "yellow", "error": "red"}.get(level, "white")
        _console.print(f"[{color}][render_cards][/{color}] {msg}")
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[render_cards] {msg}")

# ── 디자인 상수 ────────────────────────────────────────────────────────────────
_CANVAS_W = 1920
_CANVAS_H = 1080

_BG_COLORS: dict[str, str] = {
    "def":  "#1B2A3A",   # 정의 — 짙은 청회색
    "case": "#1B3A23",   # 사례 — 짙은 녹색
    "warn": "#3A1F1B",   # 주의 — 진적갈색
}

_ACCENT_COLORS: dict[str, str] = {
    "def":  "#5B8DB8",   # 청색 계열 강조
    "case": "#5BAA6E",   # 녹색 계열 강조
    "warn": "#B85B5B",   # 적색 계열 강조
}

_KIND_LABELS: dict[str, str] = {
    "def":  "정의",
    "case": "사례",
    "warn": "주의",
}

_TEXT_COLOR   = "#E8E8E8"
_TITLE_SIZE   = 80
_BODY_SIZE    = 48
_LABEL_SIZE   = 36
_PADDING_X    = 120
_PADDING_Y    = 80
_CARD_MARGIN  = 60    # 카드 내부 여백


def _load_font(role: str, size: int):
    """font_registry를 통해 폰트를 로드한다.

    role: font_manifest.json의 role key ("card", "body", "caption" 등)
    """
    import sys as _sys
    _pipelines_dir = str(Path(__file__).parent)
    if _pipelines_dir not in _sys.path:
        _sys.path.insert(0, _pipelines_dir)
    import font_registry as _fr
    return _fr.load_pil_font(role, size)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _draw_rounded_rect(draw, xy: tuple, radius: int, fill: str) -> None:
    """PIL 에 rounded rectangle 를 그린다 (PIL 9.2+ 지원, 이전 버전 폴백)."""
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill)
    except AttributeError:
        draw.rectangle(xy, fill=fill)


def render_highlight_card(
    kind: CardKind,
    title: str,
    body: str,
    out_path: Path,
) -> Path:
    """하이라이트 카드를 Pillow로 1920×1080 PNG로 렌더링한다.

    Args:
        kind: 카드 종류 — "def"(정의), "case"(사례), "warn"(주의).
        title: 카드 제목 (80pt).
        body: 카드 본문 (48pt), 자동 줄바꿈 처리.
        out_path: 출력 PNG 파일 경로.

    Returns:
        생성된 PNG 파일의 절대 경로.
    """
    assert kind in ("def", "case", "warn"), f"잘못된 kind 값: {kind!r}"

    from PIL import Image, ImageDraw

    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    bg_rgb  = _hex_to_rgb(_BG_COLORS[kind])
    acc_rgb = _hex_to_rgb(_ACCENT_COLORS[kind])
    txt_rgb = _hex_to_rgb(_TEXT_COLOR)

    canvas = Image.new("RGB", (_CANVAS_W, _CANVAS_H), bg_rgb)
    draw   = ImageDraw.Draw(canvas)

    font_label = _load_font("caption", _LABEL_SIZE)
    font_title = _load_font("card", _TITLE_SIZE)
    font_body  = _load_font("body", _BODY_SIZE)

    # ── 좌측 강조 바 ──────────────────────────────────────────────────────────
    bar_w = 12
    draw.rectangle(
        [_PADDING_X - 40, _PADDING_Y, _PADDING_X - 40 + bar_w, _CANVAS_H - _PADDING_Y],
        fill=acc_rgb,
    )

    # ── 종류 레이블 ───────────────────────────────────────────────────────────
    label_text = f"▌ {_KIND_LABELS[kind]}"
    draw.text((_PADDING_X, _PADDING_Y), label_text, font=font_label, fill=acc_rgb)

    label_bbox = font_label.getbbox(label_text)
    label_h = (label_bbox[3] - label_bbox[1]) if label_bbox else _LABEL_SIZE
    title_y = _PADDING_Y + label_h + 30

    # ── 제목 ─────────────────────────────────────────────────────────────────
    max_title_w = _CANVAS_W - _PADDING_X * 2
    title_wrapped = _wrap_text(title, font_title, max_title_w)
    draw.text((_PADDING_X, title_y), title_wrapped, font=font_title, fill=txt_rgb)

    title_bbox = font_title.getbbox(title_wrapped)
    title_h = _multiline_height(title_wrapped, font_title)
    body_y = title_y + title_h + 40

    # ── 구분선 ────────────────────────────────────────────────────────────────
    draw.rectangle(
        [_PADDING_X, body_y - 20, _CANVAS_W - _PADDING_X, body_y - 17],
        fill=_hex_to_rgb("#444444"),
    )

    # ── 본문 ─────────────────────────────────────────────────────────────────
    max_body_w = _CANVAS_W - _PADDING_X * 2
    body_wrapped = _wrap_text(body, font_body, max_body_w)
    draw.multiline_text(
        (_PADDING_X, body_y),
        body_wrapped,
        font=font_body,
        fill=txt_rgb,
        spacing=12,
    )

    canvas.save(str(out_path), "PNG")
    _log(f"저장 완료 [{kind}]: {out_path}")
    return out_path


def _wrap_text(text: str, font, max_width: int) -> str:
    """텍스트를 max_width 에 맞게 줄바꿈한다."""
    words = text.split()
    lines: list[str] = []
    current: list[str] = []

    for word in words:
        test_line = " ".join(current + [word])
        bbox = font.getbbox(test_line)
        w = bbox[2] - bbox[0] if bbox else 0
        if w <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]

    if current:
        lines.append(" ".join(current))

    return "\n".join(lines)


def _multiline_height(text: str, font) -> int:
    """여러 줄 텍스트의 전체 높이를 계산한다."""
    lines = text.split("\n")
    total = 0
    for line in lines:
        bbox = font.getbbox(line or "A")
        total += (bbox[3] - bbox[1]) if bbox else font.size
    return total + max(0, (len(lines) - 1) * 12)  # 줄 간격 12


def main() -> None:
    p = argparse.ArgumentParser(
        prog="render_cards.py",
        description="하이라이트 카드(def/case/warn) → PNG 렌더링.",
    )
    p.add_argument("--kind", choices=["def", "case", "warn"], required=True, help="카드 종류")
    p.add_argument("--title", required=True, help="카드 제목")
    p.add_argument("--body", required=True, help="카드 본문")
    p.add_argument("--out", required=True, metavar="FILE", help="출력 PNG 경로")
    args = p.parse_args()

    render_highlight_card(args.kind, args.title, args.body, Path(args.out))


if __name__ == "__main__":
    main()
