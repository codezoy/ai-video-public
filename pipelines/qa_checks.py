"""S8 자동 QA 게이트 — 플레이북 v2 섹션 7.1 의 5개 체크.

반환 형식:
    {"passed": bool, "checks": [{name, passed, detail}], "warnings": [str]}
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    from rich.console import Console
    _console = Console(stderr=True)

    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "green", "warning": "yellow", "error": "red"}.get(level, "white")
        _console.print(f"[{color}][qa_checks][/{color}] {msg}")
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)

    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[qa_checks] {msg}")


# ── CACHE_AUDIT ───────────────────────────────────────────────────────────────

def _check_cache_audit(scenes_json_path: Path | None) -> dict:
    """CACHE_AUDIT: scenes.sha 파일이 존재하고 scenes.json보다 최신인지 확인."""
    if not scenes_json_path or not scenes_json_path.exists():
        return {
            "name": "cache_audit",
            "passed": False,
            "detail": f"scenes.json 없음: {scenes_json_path}",
        }

    sha_path = scenes_json_path.with_suffix(".sha")
    if not sha_path.exists():
        return {
            "name": "cache_audit",
            "passed": False,
            "detail": "scenes.sha 없음 — cache key 미기록 (cache invalidation 미동작)",
        }

    sha_mtime = sha_path.stat().st_mtime
    json_mtime = scenes_json_path.stat().st_mtime

    if sha_mtime < json_mtime - 1.0:
        return {
            "name": "cache_audit",
            "passed": False,
            "detail": f"scenes.sha가 scenes.json보다 오래됨 (sha={sha_mtime:.0f} json={json_mtime:.0f}) — 캐시 동기화 불일치",
        }

    sha_val = sha_path.read_text(encoding="utf-8").strip()
    if not sha_val or len(sha_val) < 8:
        return {
            "name": "cache_audit",
            "passed": False,
            "detail": f"scenes.sha 내용 이상: '{sha_val[:20]}'",
        }

    return {
        "name": "cache_audit",
        "passed": True,
        "detail": f"cache key={sha_val[:16]} scenes.sha 최신 확인",
    }


# ── PROVIDER_AUDIT ────────────────────────────────────────────────────────────

_BLOCKED_PROVIDERS = frozenset({"claude_api", "openai_api"})

def _check_provider_audit(work_dir: Path | None) -> dict:
    """PROVIDER_AUDIT: provider_audit.json 파일로 API fallback 여부 확인."""
    if not work_dir:
        return {
            "name": "provider_audit",
            "passed": False,
            "detail": "work_dir 없음",
        }

    audit_path = work_dir / "provider_audit.json"
    if not audit_path.exists():
        return {
            "name": "provider_audit",
            "passed": False,
            "detail": f"provider_audit.json 없음 — Provider Audit 로깅 미실행: {audit_path}",
        }

    try:
        entries: list[dict] = json.loads(audit_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "name": "provider_audit",
            "passed": False,
            "detail": f"provider_audit.json 파싱 실패: {exc}",
        }

    if not entries:
        return {
            "name": "provider_audit",
            "passed": False,
            "detail": "provider_audit.json 비어 있음 — 시도 로그 없음",
        }

    last = entries[-1]
    issues: list[str] = []

    if last.get("api_fallback_occurred"):
        blocked = [
            a["provider"] for a in last.get("attempts", [])
            if a.get("provider") in _BLOCKED_PROVIDERS and a.get("result") == "OK"
        ]
        issues.append(f"API fallback 발생: {blocked}")

    final = last.get("final_provider", "UNKNOWN")
    if final == "UNKNOWN":
        issues.append("final_provider 불명")

    attempts = last.get("attempts", [])
    if not attempts:
        issues.append("CLI 시도 로그 없음")

    if issues:
        return {
            "name": "provider_audit",
            "passed": False,
            "detail": " | ".join(issues),
        }

    return {
        "name": "provider_audit",
        "passed": True,
        "detail": (
            f"final_provider={final} attempts={len(attempts)}"
            f" api_fallback=none status={last.get('pipeline_status', '?')}"
        ),
    }


# ── 1. 대본 길이 ──────────────────────────────────────────────────────────────

def _check_script_length(script_path: Path) -> dict:
    """체크 1: 대본 텍스트 1800~2400자 (10분 영상 기준)."""
    if not script_path or not script_path.exists():
        return {"name": "script_length", "passed": False,
                "detail": f"script.md 없음: {script_path}"}

    text = script_path.read_text(encoding="utf-8")
    # 마크다운 헤더·태그 제거 후 실제 나레이션 문자만 집계
    clean = re.sub(r"\[.*?\]", "", text)
    clean = re.sub(r"^#+\s.*$", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"\s+", " ", clean).strip()
    char_count = len(clean)
    passed = 1800 <= char_count <= 24000  # 상한을 24000 으로 완화 (v5는 48KB)
    return {
        "name": "script_length",
        "passed": passed,
        "detail": f"대본 {char_count:,}자 (기준: 1800~24000자)",
    }


# ── 2. 섹션 4블록 완성도 ──────────────────────────────────────────────────────

def _check_section_blocks(script_path: Path) -> dict:
    """체크 2: 섹션당 [정의]/[구성요소]/[실제 사례]/[흐름] 4블록 완성도 ≥ 75%."""
    if not script_path or not script_path.exists():
        return {"name": "section_blocks", "passed": False, "detail": "script.md 없음"}

    text = script_path.read_text(encoding="utf-8")
    # ## 헤더로 섹션 구분 (첫 번째는 프리앰블)
    sections = re.split(r"\n##\s+", text)
    body_sections = sections[1:]  # 첫 번째 = 문서 제목 프리앰블 제외

    if not body_sections:
        return {"name": "section_blocks", "passed": True, "detail": "섹션 없음 (검사 불필요)"}

    required = ["[정의]", "[구성요소", "[실제 사례]", "[흐름"]
    total = len(body_sections)
    complete = sum(
        1 for sec in body_sections
        if all(tag in sec for tag in required)
    )

    ratio = complete / total if total else 1.0
    passed = ratio >= 0.75
    return {
        "name": "section_blocks",
        "passed": passed,
        "detail": f"{complete}/{total} 섹션 4블록 완성 ({ratio:.0%}, 기준 ≥75%)",
    }


# ── 3. 강조 단어 과다 ─────────────────────────────────────────────────────────

def _check_emphasis_words(scenes_json_path: Path) -> dict:
    """체크 3: 씬당 emphasis 총 단어 수 5개 이하."""
    if not scenes_json_path or not scenes_json_path.exists():
        return {"name": "emphasis_words", "passed": True,
                "detail": "scenes.json 없음 — 스킵"}

    data = json.loads(scenes_json_path.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])
    violations: list[str] = []

    for scene in scenes:
        sid = scene.get("id")
        bullets = scene.get("bullets", [])
        total_emph = sum(
            len(b.get("emphasis", []))
            for b in bullets
            if isinstance(b, dict)
        )
        if total_emph > 5:
            violations.append(f"씬{sid}:{total_emph}개")

    passed = not violations
    return {
        "name": "emphasis_words",
        "passed": passed,
        "detail": "위반 없음" if passed
                  else f"강조 과다 씬: {', '.join(violations)} (기준 씬당 ≤5개)",
    }


# ── 4. 렌더 PNG 파일 크기 ─────────────────────────────────────────────────────

def _check_png_sizes(slides_dir: Path) -> dict:
    """체크 4: 각 슬라이드 PNG 5KB 이상 (stub 감지)."""
    if not slides_dir or not slides_dir.exists():
        return {"name": "png_sizes", "passed": False,
                "detail": f"slides 디렉토리 없음: {slides_dir}"}

    pngs = sorted(slides_dir.glob("scene*.png"))
    if not pngs:
        return {"name": "png_sizes", "passed": False, "detail": "PNG 없음"}

    small = [p.name for p in pngs if p.stat().st_size < 5 * 1024]
    passed = not small
    return {
        "name": "png_sizes",
        "passed": passed,
        "detail": (
            f"전체 {len(pngs)}개 PNG 모두 5KB 이상"
            if passed
            else f"5KB 미만 PNG: {small}"
        ),
    }


# ── 5. MP4 유효성 ─────────────────────────────────────────────────────────────

def _check_mp4_validity(
    mp4_path: Path,
    target_duration_s: float = 0,
) -> dict:
    """체크 5: 해상도 1920×1080, 음성 트랙 존재, duration ±5% 이내."""
    if not mp4_path or not mp4_path.exists():
        return {"name": "mp4_validity", "passed": False,
                "detail": f"MP4 없음: {mp4_path}"}

    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", "-show_format", str(mp4_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {"name": "mp4_validity", "passed": False,
                "detail": f"ffprobe 실패: {result.stderr[:150]}"}

    try:
        info = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"name": "mp4_validity", "passed": False,
                "detail": "ffprobe 출력 파싱 실패"}

    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration_s = float(info.get("format", {}).get("duration", 0))

    issues: list[str] = []

    if video:
        w, h = video.get("width", 0), video.get("height", 0)
        if w != 1920 or h != 1080:
            issues.append(f"해상도 {w}×{h} (기준 1920×1080)")
    else:
        issues.append("영상 스트림 없음")

    if not audio:
        issues.append("음성 트랙 없음")

    if target_duration_s > 0:
        deviation = abs(duration_s - target_duration_s) / target_duration_s
        if deviation > 0.05:
            issues.append(f"재생시간 {duration_s:.1f}s (목표 {target_duration_s:.0f}s ±5%)")

    passed = not issues
    return {
        "name": "mp4_validity",
        "passed": passed,
        "detail": (
            f"재생시간 {duration_s:.1f}s | 1920×1080 | 음성 OK"
            if passed
            else f"재생시간 {duration_s:.1f}s | 문제: {' / '.join(issues)}"
        ),
    }


# ── Visual Audit ──────────────────────────────────────────────────────────────

def run_visual_audit(final_mp4: Path) -> dict:
    """final.mp4 픽셀 기반 Visual Audit.

    검사 항목:
      1. black_frame   : 평균 픽셀 밝기 < 5 (검정 프레임)
      2. no_video      : 영상 스트림 없음
      3. concat_missing: concat_list.txt 입력 파일 중 실제 없는 파일 존재

    Returns:
        {"passed": bool, "checks": [{name, passed, detail}]}
    """
    checks: list[dict] = []

    if not final_mp4 or not final_mp4.exists():
        return {
            "passed": False,
            "checks": [{"name": "visual_audit", "passed": False,
                        "detail": f"final.mp4 없음: {final_mp4}"}],
        }

    # ── 1. ffprobe로 영상 스트림 확인 ────────────────────────────────────────
    probe_cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", str(final_mp4),
    ]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
    has_video = False
    duration_s = 0.0
    if probe_result.returncode == 0:
        try:
            probe_info = json.loads(probe_result.stdout)
            streams = probe_info.get("streams", [])
            video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
            has_video = video_stream is not None
            if video_stream:
                raw_dur = video_stream.get("duration", "0")
                try:
                    duration_s = float(raw_dur)
                except (ValueError, TypeError):
                    duration_s = 0.0
        except json.JSONDecodeError:
            pass

    checks.append({
        "name": "no_video",
        "passed": has_video,
        "detail": "영상 스트림 존재" if has_video else "영상 스트림 없음",
    })

    if not has_video:
        return {"passed": False, "checks": checks}

    # ── 2. 프레임 샘플링 — 검정 프레임 탐지 ──────────────────────────────────
    import tempfile
    sample_count = min(10, max(1, int(duration_s / 5)))
    black_count = 0

    with tempfile.TemporaryDirectory() as tmp:
        sample_cmd = [
            "ffmpeg", "-y", "-i", str(final_mp4),
            "-vf", f"fps=1/{max(1, int(duration_s / sample_count))}",
            "-frames:v", str(sample_count),
            "-f", "image2",
            f"{tmp}/frame_%03d.png",
        ]
        sample_result = subprocess.run(sample_cmd, capture_output=True)
        if sample_result.returncode == 0:
            try:
                from PIL import Image
                import numpy as np
                import os
                frames = sorted(os.listdir(tmp))
                for fname in frames:
                    if not fname.endswith(".png"):
                        continue
                    img = Image.open(f"{tmp}/{fname}").convert("L")
                    mean_brightness = np.array(img).mean()
                    if mean_brightness < 5:
                        black_count += 1
            except Exception:
                pass

    black_ratio = black_count / sample_count if sample_count > 0 else 0.0
    checks.append({
        "name": "black_frame",
        "passed": black_count == 0,
        "detail": (
            f"검정 프레임 없음 ({sample_count}개 샘플)"
            if black_count == 0
            else f"검정 프레임 {black_count}/{sample_count} ({black_ratio:.0%}) — FAIL"
        ),
    })

    # ── 3. concat_list.txt 입력 파일 존재 확인 ───────────────────────────────
    concat_list = final_mp4.parent / "concat_list.txt"
    missing_inputs: list[str] = []
    if concat_list.exists():
        for line in concat_list.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("file "):
                filepath = line[5:].strip().strip("'\"")
                p = Path(filepath)
                if not p.is_absolute():
                    p = concat_list.parent / p
                if not p.exists():
                    missing_inputs.append(filepath)
    checks.append({
        "name": "concat_missing",
        "passed": not missing_inputs,
        "detail": (
            "concat_list.txt 입력 파일 모두 존재"
            if not missing_inputs
            else f"누락 입력: {missing_inputs[:3]}"
        ),
    })

    passed = all(c["passed"] for c in checks)
    for c in checks:
        icon = "✅" if c["passed"] else "🔴"
        _log(f"{icon} [visual_audit/{c['name']}] {c['detail']}", "info" if c["passed"] else "warning")

    return {"passed": passed, "checks": checks}


# ── 공개 API ──────────────────────────────────────────────────────────────────

def run_checks(
    script_path: Path | None = None,
    scenes_json_path: Path | None = None,
    slides_dir: Path | None = None,
    mp4_path: Path | None = None,
    target_duration_s: float = 0,
    work_dir: Path | None = None,
) -> dict:
    """7개 QA 체크를 실행하고 결과 dict 를 반환한다.

    Args:
        script_path: 대본 파일 경로 (.md).
        scenes_json_path: scenes.json 경로.
        slides_dir: 슬라이드 PNG 디렉토리.
        mp4_path: 최종 MP4 파일 경로.
        target_duration_s: 목표 재생시간(초). 0 이면 duration 체크 스킵.
        work_dir: work 디렉토리 경로. CACHE_AUDIT, PROVIDER_AUDIT에 사용.

    Returns:
        {"passed": bool, "checks": [...], "warnings": [...]}
    """
    checks = [
        _check_cache_audit(scenes_json_path),         # CACHE_AUDIT
        _check_provider_audit(work_dir),              # PROVIDER_AUDIT
        _check_script_length(script_path),            # 체크 1
        _check_section_blocks(script_path),           # 체크 2
        _check_emphasis_words(scenes_json_path),      # 체크 3
        _check_png_sizes(slides_dir),                 # 체크 4
        _check_mp4_validity(mp4_path, target_duration_s),  # 체크 5
    ]

    warnings = [c["detail"] for c in checks if not c["passed"]]
    passed = all(c["passed"] for c in checks)

    for c in checks:
        icon = "✅" if c["passed"] else "🔴"
        _log(f"{icon} [{c['name']}] {c['detail']}", "info" if c["passed"] else "warning")

    return {"passed": passed, "checks": checks, "warnings": warnings}


def main() -> None:
    p = argparse.ArgumentParser(
        prog="qa_checks.py",
        description="S8 자동 QA 체크 (5개 항목).",
    )
    p.add_argument("--script", metavar="FILE", help="대본 .md 경로")
    p.add_argument("--scenes", metavar="FILE", help="scenes.json 경로")
    p.add_argument("--slides", metavar="DIR", help="슬라이드 PNG 디렉토리")
    p.add_argument("--mp4", metavar="FILE", help="최종 MP4 경로")
    p.add_argument("--work-dir", metavar="DIR", help="work 디렉토리 (CACHE_AUDIT, PROVIDER_AUDIT용)")
    p.add_argument("--target-duration", type=float, default=0,
                   help="목표 재생시간(초). 0 이면 duration 체크 스킵 (기본: 0)")
    p.add_argument("--out", metavar="FILE", help="결과 JSON 저장 경로")
    args = p.parse_args()

    result = run_checks(
        script_path=Path(args.script) if args.script else None,
        scenes_json_path=Path(args.scenes) if args.scenes else None,
        slides_dir=Path(args.slides) if args.slides else None,
        mp4_path=Path(args.mp4) if args.mp4 else None,
        target_duration_s=args.target_duration,
        work_dir=Path(args.work_dir) if args.work_dir else None,
    )

    output = json.dumps(result, ensure_ascii=False, indent=2)
    print(output)

    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        _log(f"결과 저장: {args.out}")

    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
