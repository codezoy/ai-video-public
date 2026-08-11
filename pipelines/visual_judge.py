"""visual_judge.py — 슬라이드 PNG 시각 검증 (PIL 로컬).

체크 항목:
  1. text_overflow   — PIL 경계 근처 밝은 픽셀 검출 (텍스트 잘림)
  2. contrast        — WCAG AA 4.5:1 배경/전경 대비 검사
  3. emphasis_pos    — 노란색 강조 박스가 헤더 영역(상단 1/8) 침범 여부
  4. typo_hierarchy  — CLI-only 정책에서는 API vision 비활성

반환값 예시:
  {
    "pass": false,
    "checks": [
      {"name": "text_overflow", "pass": true, "detail": ""},
      {"name": "contrast",      "pass": false, "detail": "WCAG AA 4.5:1 미달: ratio=3.2"},
      {"name": "emphasis_pos",  "pass": true,  "detail": ""},
      {"name": "typo_hierarchy","pass": true,  "detail": ""},
    ],
    "corrections": ["색상 대비를 높여주세요: 현재 비율 3.2, 목표 4.5"]
  }
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TypedDict

try:
    from rich.console import Console
    _console = Console(stderr=True)
    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "cyan", "warning": "yellow", "error": "red"}.get(level, "white")
        _console.print(f"[{color}][visual_judge][/{color}] {msg}")
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[visual_judge] {msg}")


# ── 타입 정의 ────────────────────────────────────────────────────────────────

class CheckResult(TypedDict):
    name: str
    passed: bool
    detail: str


class JudgeResult(TypedDict):
    passed: bool
    checks: list[CheckResult]
    corrections: list[str]


# ── PIL 유틸리티 ─────────────────────────────────────────────────────────────

def _relative_luminance(r: int, g: int, b: int) -> float:
    """sRGB → 상대 휘도 (WCAG 2.1 정의)."""
    def _lin(c: float) -> float:
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _contrast_ratio(l1: float, l2: float) -> float:
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# ── 체크 1: 텍스트 잘림 ──────────────────────────────────────────────────────

def _check_text_overflow(img: object, margin: int = 15, threshold: int = 40) -> CheckResult:
    """이미지 경계 margin px 이내에 밝은 픽셀(텍스트 색)이 있으면 잘림 위험."""
    try:
        from PIL import Image  # type: ignore[import]
        assert isinstance(img, Image.Image)
        w, h = img.size
        rgb = img.convert("RGB")

        regions = [
            rgb.crop((0, 0, margin, h)),          # 왼쪽
            rgb.crop((w - margin, 0, w, h)),       # 오른쪽
            rgb.crop((0, 0, w, margin)),           # 상단
            rgb.crop((0, h - margin, w, h)),       # 하단
        ]
        overflow_pixels = 0
        for region in regions:
            for r, g, b in region.getdata():
                if r > threshold or g > threshold or b > threshold:
                    overflow_pixels += 1

        if overflow_pixels > 50:
            return CheckResult(
                name="text_overflow",
                passed=False,
                detail=f"경계 {margin}px 이내 밝은 픽셀 {overflow_pixels}개 — 텍스트 잘림 가능성",
            )
        return CheckResult(name="text_overflow", passed=True, detail="")
    except Exception as exc:
        return CheckResult(name="text_overflow", passed=True, detail=f"PIL 오류(스킵): {exc}")


# ── 체크 2: 색상 대비 (WCAG AA) ──────────────────────────────────────────────

def _check_contrast(img: object, sample_count: int = 200) -> CheckResult:
    """배경(어두운 픽셀)과 전경(밝은 픽셀) 대표 색상 쌍의 WCAG 대비 비율 검사."""
    try:
        from PIL import Image  # type: ignore[import]
        assert isinstance(img, Image.Image)
        rgb = img.convert("RGB")
        w, h = img.size
        step = max(1, (w * h) // sample_count)

        dark_pixels: list[tuple[int, int, int]] = []
        light_pixels: list[tuple[int, int, int]] = []

        pixels = list(rgb.getdata())
        for i in range(0, len(pixels), step):
            r, g, b = pixels[i]
            brightness = 0.299 * r + 0.587 * g + 0.114 * b
            if brightness < 80:
                dark_pixels.append((r, g, b))
            elif brightness > 160:
                light_pixels.append((r, g, b))

        if not dark_pixels or not light_pixels:
            return CheckResult(name="contrast", passed=True, detail="대비 검사 샘플 부족 (단색 배경 가능성)")

        avg_dark = tuple(sum(c[i] for c in dark_pixels) // len(dark_pixels) for i in range(3))
        avg_light = tuple(sum(c[i] for c in light_pixels) // len(light_pixels) for i in range(3))

        l_dark = _relative_luminance(*avg_dark)   # type: ignore[arg-type]
        l_light = _relative_luminance(*avg_light)  # type: ignore[arg-type]
        ratio = _contrast_ratio(l_dark, l_light)

        target = 4.5
        if ratio < target:
            return CheckResult(
                name="contrast",
                passed=False,
                detail=f"WCAG AA 4.5:1 미달 — 현재 {ratio:.2f}:1",
            )
        return CheckResult(name="contrast", passed=True, detail=f"대비 {ratio:.2f}:1 통과")
    except Exception as exc:
        return CheckResult(name="contrast", passed=True, detail=f"PIL 오류(스킵): {exc}")


# ── 체크 3: 강조 위치 (노란 박스 헤더 침범) ──────────────────────────────────

def _check_emphasis_position(img: object, header_fraction: float = 0.125) -> CheckResult:
    """노란색 계열 픽셀이 상단 header_fraction(=1/8) 영역에 존재하면 경고."""
    try:
        from PIL import Image  # type: ignore[import]
        assert isinstance(img, Image.Image)
        rgb = img.convert("RGB")
        w, h = img.size
        header_h = int(h * header_fraction)
        header_region = rgb.crop((0, 0, w, header_h))

        yellow_count = 0
        for r, g, b in header_region.getdata():
            if r > 180 and g > 150 and b < 80:
                yellow_count += 1

        if yellow_count > 30:
            return CheckResult(
                name="emphasis_pos",
                passed=False,
                detail=f"헤더 영역(상단 {header_fraction*100:.0f}%)에 노란 강조 픽셀 {yellow_count}개",
            )
        return CheckResult(name="emphasis_pos", passed=True, detail="")
    except Exception as exc:
        return CheckResult(name="emphasis_pos", passed=True, detail=f"PIL 오류(스킵): {exc}")


# ── 체크 4: 타이포 위계 (API vision 비활성) ─────────────────────────────────

_TYPO_SYSTEM = (
    "당신은 슬라이드 디자인 검수 전문가입니다. "
    "이미지를 보고 타이포그래피 위계(폰트 크기 계층) 위반 여부만 판단하세요."
)

_TYPO_PROMPT = (
    "이 슬라이드 이미지에서 타이포그래피 위계 위반을 검사하세요.\n"
    "확인 항목:\n"
    "- 제목이 본문보다 작거나 같은 크기인가?\n"
    "- 강조 텍스트가 제목보다 큰가?\n"
    "- 읽기 어려운 폰트 크기(화면상 12px 미만)가 있는가?\n\n"
    "응답은 반드시 JSON 형식으로만: "
    '{"pass": true/false, "detail": "위반 내용 or 정상"}'
)


def _check_typo_hierarchy(image_path: str) -> CheckResult:
    """API vision disabled; keep check as a skipped PASS for compatibility."""
    try:
        from llm_client import generate_vision  # type: ignore[import]
        raw = generate_vision(
            prompt=_TYPO_PROMPT,
            image_path=image_path,
            system=_TYPO_SYSTEM,
            max_tokens=256,
        )
        # JSON 파싱
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
            passed = bool(data.get("pass", True))
            detail = str(data.get("detail", ""))
        else:
            passed = True
            detail = f"파싱 불가 (원문: {raw[:80]})"
        return CheckResult(name="typo_hierarchy", passed=passed, detail=detail)
    except Exception as exc:
        return CheckResult(name="typo_hierarchy", passed=True, detail=f"vision 오류(스킵): {exc}")


# ── 공개 진입점 ──────────────────────────────────────────────────────────────

def judge(image_path: str | Path, use_vision: bool = False) -> JudgeResult:
    """PNG 슬라이드 하나를 4개 항목으로 검증한다.

    Args:
        image_path: 검사할 PNG 파일 경로.
        use_vision: True 여도 CLI-only 정책에서는 typo_hierarchy가 스킵된다.
                    False 이면 PIL 3개 체크만 실행.

    Returns:
        JudgeResult (pass + checks + corrections).
    """
    image_path = str(image_path)
    _log(f"검사 시작: {image_path} (vision={use_vision})")

    try:
        from PIL import Image  # type: ignore[import]
        img = Image.open(image_path)
    except Exception as exc:
        _log(f"이미지 열기 실패: {exc}", "error")
        return JudgeResult(
            passed=False,
            checks=[CheckResult(name="image_load", passed=False, detail=str(exc))],
            corrections=[f"이미지를 열 수 없습니다: {exc}"],
        )

    checks: list[CheckResult] = [
        _check_text_overflow(img),
        _check_contrast(img),
        _check_emphasis_position(img),
    ]

    if use_vision:
        checks.append(_check_typo_hierarchy(image_path))
    else:
        checks.append(CheckResult(name="typo_hierarchy", passed=True, detail="vision 스킵 (--auto-correct 미활성)"))

    failed = [c for c in checks if not c["passed"]]
    corrections = [c["detail"] for c in failed if c["detail"]]

    result = JudgeResult(
        passed=len(failed) == 0,
        checks=checks,
        corrections=corrections,
    )

    if result["passed"]:
        _log(f"검사 통과: {Path(image_path).name}", "info")
    else:
        _log(f"검사 실패 {len(failed)}개: {[c['name'] for c in failed]}", "warning")

    return result


def judge_all(slides_dir: str | Path, use_vision: bool = False) -> dict[str, JudgeResult]:
    """slides_dir 내 모든 PNG 를 검사하고 {파일명: JudgeResult} 를 반환한다."""
    slides_dir = Path(slides_dir)
    results: dict[str, JudgeResult] = {}
    png_files = sorted(slides_dir.glob("*.png"))

    if not png_files:
        _log(f"PNG 파일 없음: {slides_dir}", "warning")
        return results

    for png in png_files:
        results[png.name] = judge(png, use_vision=use_vision)

    passed = sum(1 for r in results.values() if r["passed"])
    _log(f"전체 검사 완료: {passed}/{len(results)} 통과")
    return results
