"""S6 시각 자산 — 코드/명령어를 Pygments로 하이라이팅해 PNG로 렌더링한다.

의존성: pygments, Pillow
설치: pip install pygments Pillow
참조: 플레이북 v2 섹션 6.3 (코드 하이라이팅)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from rich.console import Console
    _console = Console(stderr=True)
    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "green", "warning": "yellow", "error": "red"}.get(level, "white")
        _console.print(f"[{color}][render_code][/{color}] {msg}")
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[render_code] {msg}")

# ── 상수 ─────────────────────────────────────────────────────────────────────
_BG_COLOR = "#0B0B0B"
_CANVAS_W = 1920
_CANVAS_H = 1080
_PADDING_X = 80
_PADDING_Y = 60
_FONT_SIZE = 28

def _load_mono_font(size: int):
    """font_manifest.json의 'code' role에서 폰트를 로드한다."""
    _pipelines_dir = str(Path(__file__).parent)
    if _pipelines_dir not in sys.path:
        sys.path.insert(0, _pipelines_dir)
    try:
        import font_registry as _fr
        return _fr.load_pil_font("code", size)
    except Exception as exc:
        _log(f"font_registry 'code' 로드 실패: {exc}", "error")
        raise RuntimeError(f"코드 렌더 폰트 로드 불가: {exc}") from exc


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def code_to_png(
    code: str,
    language: str,
    out_path: Path,
) -> Path:
    """소스 코드를 Pygments + Pillow로 렌더링해 PNG로 저장한다.

    Args:
        code: 렌더링할 소스 코드 또는 명령어 문자열.
        language: Pygments lexer 이름.
            예: "python", "bash", "json", "shell-session".
        out_path: 출력 PNG 파일 경로.

    Returns:
        생성된 PNG 파일의 절대 경로.
    """
    from PIL import Image, ImageDraw
    from pygments import highlight
    from pygments.formatters import ImageFormatter
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.styles import get_style_by_name

    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # lexer 결정
    try:
        lexer = get_lexer_by_name(language, stripall=True)
    except Exception:
        _log(f"lexer '{language}' 불명 → 자동 감지", "warning")
        lexer = guess_lexer(code)

    # Pygments ImageFormatter 로 코드 영역 PNG 생성
    font = _load_mono_font(_FONT_SIZE)
    _pipelines_dir = str(Path(__file__).parent)
    if _pipelines_dir not in sys.path:
        sys.path.insert(0, _pipelines_dir)
    import font_registry as _fr_code
    font_path = str(_fr_code.resolve_font_path("code"))

    fmt_kwargs: dict = {
        "style": "monokai",
        "font_size": _FONT_SIZE,
        "line_numbers": True,
        "line_number_bg": "#111111",
        "line_number_fg": "#666666",
        "hl_lines": [],
        "image_pad": 20,
        "line_pad": 4,
        "font_name": font_path,
    }

    formatter = ImageFormatter(**fmt_kwargs)

    # Pygments 가 반환하는 raw bytes → PIL Image
    import io
    raw_bytes = highlight(code, lexer, formatter)
    code_img = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")

    # 1920×1080 캔버스에 중앙 배치
    canvas = Image.new("RGBA", (_CANVAS_W, _CANVAS_H), _hex_to_rgb(_BG_COLOR) + (255,))
    draw = ImageDraw.Draw(canvas)

    # 코드 이미지가 캔버스보다 크면 비율 유지 축소
    max_w = _CANVAS_W - _PADDING_X * 2
    max_h = _CANVAS_H - _PADDING_Y * 2
    cw, ch = code_img.size
    scale = min(max_w / cw, max_h / ch, 1.0)
    if scale < 1.0:
        new_w = int(cw * scale)
        new_h = int(ch * scale)
        code_img = code_img.resize((new_w, new_h), Image.LANCZOS)
        cw, ch = new_w, new_h

    # 수직 중앙 정렬
    paste_x = (_CANVAS_W - cw) // 2
    paste_y = (_CANVAS_H - ch) // 2

    # 코드 배경 약간 둥근 사각형 (단순 직사각형으로 처리)
    canvas.paste(code_img, (paste_x, paste_y), code_img)

    canvas.convert("RGB").save(str(out_path), "PNG")
    _log(f"저장 완료: {out_path}")
    return out_path


def main() -> None:
    p = argparse.ArgumentParser(
        prog="render_code.py",
        description="코드/명령어를 Pygments 하이라이팅으로 PNG 렌더링.",
    )
    p.add_argument("--code", metavar="CODE", help="렌더링할 코드 문자열")
    p.add_argument("--input", metavar="FILE", help="렌더링할 코드 파일 경로")
    p.add_argument("--lang", default="python", metavar="LANG", help="Pygments lexer 이름 (기본: python)")
    p.add_argument("--out", required=True, metavar="FILE", help="출력 PNG 경로")
    args = p.parse_args()

    if not args.code and not args.input:
        print("[render_code] --code 또는 --input 중 하나를 지정하세요.", file=sys.stderr)
        sys.exit(1)

    code = Path(args.input).read_text(encoding="utf-8") if args.input else args.code
    code_to_png(code, args.lang, Path(args.out))


if __name__ == "__main__":
    main()
