"""S7-unit final concatenator — scene_NN.mp4 → final.mp4.

Concatenates per-scene MP4 files produced by scene_render.py into a single
final.mp4 using ffmpeg concat demuxer (stream copy — no re-encode).

Concat flow:
    work/scenes/scene01.mp4
    work/scenes/scene02.mp4
    ...
           ↓ concat_list.txt
    ffmpeg -f concat -safe 0 -i concat_list.txt -c copy final.mp4

Scene Object fields read:
    render_path   – per-scene MP4 path (v2 field; required when scenes are passed)
    id            – scene identifier (for logging)

Output:
    final.mp4 at the specified output path
    concat_list.txt alongside it (or at a custom path)
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from rich.console import Console
    _console = Console(stderr=True)

    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "cyan", "warning": "yellow", "error": "red",
                 "success": "green"}.get(level, "white")
        _console.print(f"[{color}][final_concat][/{color}] {msg}")
except ImportError:
    logging.basicConfig(level=logging.INFO)
    _logger = logging.getLogger("final_concat")

    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logger, level, _logger.info)(f"[final_concat] {msg}")


ROOT       = Path(os.environ.get("PROJECT_ROOT", Path(__file__).parent.parent))
WORK_DIR   = Path(os.getenv("WORK_DIR",  str(ROOT / "work")))
FFMPEG_BIN = os.getenv("FFMPEG_BIN", shutil.which("ffmpeg") or "ffmpeg")
FFMPEG_TIMEOUT_SEC = int(os.getenv("FFMPEG_TIMEOUT_SEC", "120"))


# ── concat_list helpers ───────────────────────────────────────────────────────

def build_concat_list(mp4_paths: list[Path], list_path: Path) -> Path:
    """Write an ffmpeg concat demuxer list file.

    Each line is ``file '<absolute_path>'`` — absolute paths bypass the
    ``-safe 0`` restriction but we pass ``-safe 0`` anyway for robustness.

    Args:
        mp4_paths:  Ordered list of MP4 file paths.
        list_path:  Destination path for the concat_list.txt file.

    Returns:
        list_path on success.

    Raises:
        ValueError: mp4_paths is empty.
        FileNotFoundError: Any mp4 in the list does not exist.
    """
    if not mp4_paths:
        raise ValueError("concat_list: mp4_paths가 비어 있습니다")

    missing = [p for p in mp4_paths if not p.exists()]
    if missing:
        names = ", ".join(str(p) for p in missing[:5])
        raise FileNotFoundError(
            f"concat_list: 다음 MP4 파일이 없습니다 → {names}"
        )

    list_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"file '{p.resolve()}'" for p in mp4_paths]
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _log(f"concat_list 작성 완료 ({len(mp4_paths)}개) → {list_path}")
    return list_path


# ── ffmpeg helpers ────────────────────────────────────────────────────────────

def _run_ffmpeg_concat(
    list_path: Path,
    output_path: Path,
) -> None:
    """Execute ffmpeg concat demuxer. Raises RuntimeError on failure."""
    import time as _time
    cmd = [
        FFMPEG_BIN, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_path),
        "-c", "copy",
        str(output_path),
    ]
    t0 = _time.monotonic()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SEC
        )
    except subprocess.TimeoutExpired:
        elapsed = _time.monotonic() - t0
        print(
            f"[STAGE_TIMEOUT] stage=ffmpeg_concat limit_sec={FFMPEG_TIMEOUT_SEC}"
            f" elapsed_sec={elapsed:.0f} status=FAIL",
            flush=True,
        )
        raise RuntimeError(
            f"ffmpeg concat timeout ({FFMPEG_TIMEOUT_SEC}s)"
        )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg concat 실패:\n{result.stderr[-800:]}"
        )


# ── Core API ──────────────────────────────────────────────────────────────────

def concat_scenes(
    mp4_paths: list[Path],
    output_path: Path,
    *,
    concat_list_path: Path | None = None,
    force: bool = False,
) -> Path:
    """Concatenate scene MP4 files into a single final.mp4.

    Uses ffmpeg concat demuxer with stream copy — no re-encoding.

    Args:
        mp4_paths:         Ordered list of per-scene MP4 paths.
        output_path:       Destination final.mp4 path.
        concat_list_path:  Override path for concat_list.txt.
                           Defaults to ``output_path.parent / "concat_list.txt"``.
        force:             Re-concatenate even if output already exists.

    Returns:
        output_path on success.

    Raises:
        ValueError:        mp4_paths is empty.
        FileNotFoundError: Any scene MP4 missing.
        RuntimeError:      ffmpeg failure.
    """
    if output_path.exists() and not force:
        _log(f"skip (캐시 존재) → {output_path.name}", "warning")
        return output_path

    list_path = concat_list_path or (output_path.parent / "concat_list.txt")
    build_concat_list(mp4_paths, list_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _log(f"ffmpeg concat 시작 ({len(mp4_paths)}개 씬) → {output_path.name}")
    _run_ffmpeg_concat(list_path, output_path)

    _log(
        f"concat 완료 → {output_path} "
        f"({output_path.stat().st_size // 1024} KB)",
        "success",
    )
    return output_path


def concat_from_scenes(
    scenes: list[dict[str, Any]],
    output_path: Path,
    *,
    concat_list_path: Path | None = None,
    force: bool = False,
    scenes_dir: Path | None = None,
) -> Path:
    """Concatenate using Scene Object list (reads render_path from each scene).

    Scene Object v2 compatible: reads ``render_path`` field from each scene.
    Falls back to ``scenes_dir/scene{id:02d}.mp4`` (or ``work/scenes/`` if not provided).

    Args:
        scenes:      list of Scene Object dicts (v1 or v2).
        output_path: Destination final.mp4 path.
        concat_list_path: Override path for concat_list.txt.
        force:       Re-concatenate even if output already exists.
        scenes_dir:  Override fallback directory for scene mp4 files.

    Returns:
        output_path on success.
    """
    _fallback_dir = scenes_dir if scenes_dir is not None else WORK_DIR / "scenes"
    mp4_paths: list[Path] = []
    for scene in scenes:
        sid = scene.get("id", 0)
        render_rp = scene.get("render_path")

        # render_path 단일 경로 사용 (captioned_path는 DEPRECATED — LEGACY_CAPTION_OVERLAY 모드 전용)
        if render_rp and Path(render_rp).exists():
            chosen = Path(render_rp)
        else:
            try:
                sid_int = int(sid)
                chosen = _fallback_dir / f"scene{sid_int:02d}.mp4"
            except (ValueError, TypeError):
                chosen = _fallback_dir / f"{sid}.mp4"
            _log(f"씬 {sid}: render_path 없음 → fallback {chosen.name}", "warning")

        print(
            f"[FINAL_CONCAT_INPUT] scene={sid} path={chosen} captioned=false",
            flush=True,
        )
        mp4_paths.append(chosen)

    return concat_scenes(
        mp4_paths,
        output_path,
        concat_list_path=concat_list_path,
        force=force,
    )


# ── CLI entry ─────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    p = argparse.ArgumentParser(
        prog="final_concat.py",
        description="S7-unit — scene_NN.mp4 → final.mp4 via ffmpeg concat.",
    )
    p.add_argument(
        "--scenes-json", type=Path,
        default=WORK_DIR / "scenes.json",
        help="scenes.json 경로 (기본: work/scenes.json)",
    )
    p.add_argument(
        "--scenes-dir", type=Path,
        default=WORK_DIR / "scenes",
        help="씬 MP4 디렉토리 (--scenes-json 없을 때 사용, 기본: work/scenes/)",
    )
    p.add_argument(
        "--output", type=Path,
        default=WORK_DIR / "final.mp4",
        help="최종 MP4 출력 경로 (기본: work/final.mp4)",
    )
    p.add_argument(
        "--concat-list", type=Path, default=None,
        help="concat_list.txt 경로 (기본: output 디렉토리)",
    )
    p.add_argument("--force", action="store_true", help="캐시 무시, 재실행")
    p.add_argument("--dry-run", action="store_true", help="입력 검증만 수행")
    args = p.parse_args()

    # ── Resolve scene MP4 list ─────────────────────────────────────────────────
    if args.scenes_json.exists():
        data   = json.loads(args.scenes_json.read_text(encoding="utf-8"))
        scenes = data.get("scenes", [])
        if not scenes:
            _log("씬이 없습니다", "warning")
            sys.exit(0)

        if args.dry_run:
            _log(f"dry-run: {len(scenes)} 씬 검증")
            for scene in scenes:
                sid = scene.get("id", "?")
                rp  = scene.get("render_path", "MISSING")
                ok  = "OK" if rp != "MISSING" and Path(rp).exists() else "MISSING"
                _log(f"  씬 {sid}: render_path={ok} ({rp})")
            return

        concat_from_scenes(
            scenes,
            args.output,
            concat_list_path=args.concat_list,
            force=args.force,
        )
    else:
        # Fallback: glob scene MP4 files from --scenes-dir
        if not args.scenes_dir.exists():
            _log(f"scenes-dir 없음: {args.scenes_dir}", "error")
            sys.exit(1)

        mp4_paths = sorted(args.scenes_dir.glob("scene*.mp4"))
        if not mp4_paths:
            _log(f"scene*.mp4 파일 없음: {args.scenes_dir}", "error")
            sys.exit(1)

        if args.dry_run:
            _log(f"dry-run: {len(mp4_paths)} MP4 파일 발견")
            for p in mp4_paths:
                _log(f"  {p.name} ({p.stat().st_size // 1024} KB)")
            return

        concat_scenes(
            mp4_paths,
            args.output,
            concat_list_path=args.concat_list,
            force=args.force,
        )


if __name__ == "__main__":
    main()
