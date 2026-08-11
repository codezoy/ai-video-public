"""font_registry.py — AI-Video 전체 렌더 경로 단일 Font Registry.

assets/font_manifest.json을 단일 소스로 로드하고,
PIL ImageFont 생성 / 경로 해결 / Audit 출력을 담당한다.

모든 파이프라인은 이 모듈을 통해서만 폰트를 로드한다.
개별 _FONT_PATHS 리스트 관리 및 fallback 탐색 금지.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# PROJECT_ROOT: 이 파일이 pipelines/ 에 있으므로 한 단계 위
_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).parent.parent))
_MANIFEST_PATH = _ROOT / "assets" / "font_manifest.json"

# ALLOW_FONT_FALLBACK=true 일 때만 시스템 fallback 허용 (기본 false)
_ALLOW_FALLBACK = os.environ.get("ALLOW_FONT_FALLBACK", "false").lower() == "true"

_manifest_cache: dict[str, Any] | None = None


# ── Public API ────────────────────────────────────────────────────────────────

def load_font_manifest() -> dict[str, Any]:
    """assets/font_manifest.json을 로드하고 캐시한다."""
    global _manifest_cache
    if _manifest_cache is None:
        if not _MANIFEST_PATH.exists():
            raise FileNotFoundError(
                f"Font manifest 없음: {_MANIFEST_PATH}\n"
                "assets/font_manifest.json 파일이 존재해야 합니다."
            )
        with open(_MANIFEST_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        _manifest_cache = {k: v for k, v in raw.items() if not k.startswith("_")}
    return _manifest_cache


def get_font_spec(role: str) -> dict[str, Any]:
    """role에 해당하는 font spec dict를 반환한다.

    예: get_font_spec("title") → {"family": "Paperlogy", "weight": 800, "file": "...", ...}
    """
    manifest = load_font_manifest()
    if role not in manifest:
        raise KeyError(
            f"Font role '{role}' 없음. 등록된 role: {list(manifest.keys())}"
        )
    return manifest[role]


def resolve_font_path(role: str) -> Path:
    """role의 font 파일 절대 경로를 반환한다.

    font 파일이 없으면 ALLOW_FONT_FALLBACK=true 일 때만 시스템 폰트를 탐색한다.
    ALLOW_FONT_FALLBACK=false(기본)이면 RuntimeError를 발생시킨다.
    """
    spec = get_font_spec(role)
    primary = _ROOT / spec["file"]

    if primary.exists():
        return primary

    if _ALLOW_FALLBACK:
        # 명시적 dev fallback: 시스템 font 탐색
        system_paths = _system_fallback_paths(spec)
        for p in system_paths:
            if p.exists():
                logger.warning(
                    "[FONT_REGISTRY] role=%s primary 없음(%s) → fallback=%s",
                    role, primary, p,
                )
                return p

    raise RuntimeError(
        f"[FONT_REGISTRY] FAIL — role={role} 폰트 파일 없음: {primary}\n"
        f"ALLOW_FONT_FALLBACK=true 환경변수로 시스템 fallback 허용 가능."
    )


def load_pil_font(role: str, size: int):
    """role과 size에 맞는 PIL ImageFont를 반환한다.

    Variable font (PretendardVariable)인 경우 variation_name 인스턴스를 설정한다.
    """
    from PIL import ImageFont

    spec = get_font_spec(role)
    font_path = resolve_font_path(role)

    try:
        font = ImageFont.truetype(str(font_path), size)
    except OSError as exc:
        raise RuntimeError(
            f"[FONT_REGISTRY] FAIL — role={role} 로드 실패: {font_path}\n{exc}"
        ) from exc

    # Variable font weight instance 설정
    variation_name = spec.get("variation_name")
    if variation_name and hasattr(font, "set_variation_by_name"):
        try:
            font.set_variation_by_name(variation_name)
            logger.info(
                "[FONT_GLYPH_AUDIT] role=%s family=%s weight=%s variation=%s size=%d path=%s result=PASS",
                role, spec.get("family", "?"), spec.get("weight", "?"), variation_name, size, font_path,
            )
        except Exception as exc:
            # ALLOW_FONT_FALLBACK=false(기본): variation 실패는 FAIL — 조용한 통과 금지
            if not _ALLOW_FALLBACK:
                raise RuntimeError(
                    f"[FONT_REGISTRY] FAIL — role={role} variation={variation_name} 설정 실패: {exc}\n"
                    f"PretendardVariable.ttf에 '{variation_name}' named instance가 없습니다."
                ) from exc
            logger.warning(
                "[FONT_GLYPH_AUDIT] role=%s variation=%s 설정 실패(fallback 허용): %s",
                role, variation_name, exc,
            )
    else:
        logger.debug(
            "[FONT_REGISTRY] role=%s size=%d from %s", role, size, font_path
        )

    return font


def audit_fonts(renderer: str = "all") -> dict[str, str]:
    """모든 role의 font 파일 존재 여부를 확인하고 FONT_REGISTRY_AUDIT 로그를 출력한다.

    Returns: {role: "PASS" | "FAIL"} dict
    """
    manifest = load_font_manifest()
    results: dict[str, str] = {}

    for role, spec in manifest.items():
        font_path = _ROOT / spec["file"]
        status = "PASS" if font_path.exists() else "FAIL"
        results[role] = status

        print(
            f"[FONT_REGISTRY_AUDIT]\n"
            f"renderer={renderer}\n"
            f"role={role}\n"
            f"family={spec['family']}\n"
            f"weight={spec['weight']}\n"
            f"file={font_path}\n"
            f"result={status}"
        )

    return results


# ── Internal ──────────────────────────────────────────────────────────────────

def _system_fallback_paths(spec: dict[str, Any]) -> list[Path]:
    """ALLOW_FONT_FALLBACK=true 전용 시스템 탐색 경로."""
    home = Path.home()
    family = spec.get("family", "")
    weight = spec.get("weight", 400)

    paths: list[Path] = []

    if family == "Paperlogy":
        weight_name_map = {
            800: "8ExtraBold",
            700: "7Bold",
            600: "6SemiBold",
            500: "5Medium",
            400: "4Regular",
        }
        w_name = weight_name_map.get(weight, "7Bold")
        paths += [
            home / f"Library/Fonts/Paperlogy-{w_name}.ttf",
            Path(f"/Library/Fonts/Paperlogy-{w_name}.ttf"),
        ]
    elif family == "Pretendard":
        paths += [
            home / "Library/Fonts/PretendardVariable.ttf",
            Path("/Library/Fonts/PretendardVariable.ttf"),
            home / "Library/Fonts/Pretendard-SemiBold.ttf",
            Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
        ]

    return paths
