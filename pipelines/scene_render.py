"""S6-unit scene renderer — Scene Object → scene_NN.mp4 (per-scene).

Produces an individual MP4 for each scene using the scene's slide PNG and TTS
audio.  Enables scene-level cache and incremental re-rendering: only modified
scenes need to be re-rendered before the final concat step.

Output layout:
    work/scenes/scene_01.mp4
    work/scenes/scene_02.mp4
    ...

Scene Object fields read:
    audio_path          – TTS MP3 path (required)
    slide_path          – slide PNG path (required)
    audio_duration_sec  – v2 field; used for exact frame count
    audio_duration_ms   – v2 field; fallback if audio_duration_sec absent
    id                  – scene identifier (int or str)

Scene Object fields written (in-place):
    render_path             – absolute path of generated MP4
    render_duration_frames  – total frames = ceil(FPS × audio_duration_sec)
    stages_done             – "render" appended if not already present
"""
from __future__ import annotations

import json
import logging
import math
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
        _console.print(f"[{color}][scene_render][/{color}] {msg}")
except ImportError:
    logging.basicConfig(level=logging.INFO)
    _logger = logging.getLogger("scene_render")

    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logger, level, _logger.info)(f"[scene_render] {msg}")


ROOT        = Path(os.environ.get("PROJECT_ROOT", Path(__file__).parent.parent))
WORK_DIR    = Path(os.getenv("WORK_DIR",   str(ROOT / "work")))
VIDEO_FPS   = int(os.getenv("VIDEO_FPS",   "24"))
CANVAS_W    = int(os.getenv("VIDEO_WIDTH", "1920"))
CANVAS_H    = int(os.getenv("VIDEO_HEIGHT","1080"))
FFMPEG_BIN  = os.getenv("FFMPEG_BIN",  shutil.which("ffmpeg")  or "ffmpeg")
FFPROBE_BIN = os.getenv("FFPROBE_BIN", shutil.which("ffprobe") or "ffprobe")


# ── Duration helpers ──────────────────────────────────────────────────────────

def _ffprobe_duration(audio_path: Path) -> float | None:
    """Return audio duration in seconds via ffprobe. None on failure."""
    if not audio_path.exists():
        return None
    try:
        result = subprocess.run(
            [FFPROBE_BIN, "-v", "quiet", "-print_format", "json",
             "-show_streams", str(audio_path)],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(result.stdout)
        for stream in data.get("streams", []):
            dur = stream.get("duration")
            if dur is not None:
                return float(dur)
    except Exception as exc:
        _log(f"ffprobe 실패 ({audio_path.name}): {exc}", "warning")
    return None


def _resolve_duration(scene: dict, audio_path: Path) -> float | None:
    """Scene v2 audio_duration_sec → audio_duration_ms → ffprobe → None."""
    dur = scene.get("audio_duration_sec")
    if dur is not None:
        return float(dur)
    dur_ms = scene.get("audio_duration_ms")
    if dur_ms is not None:
        return float(dur_ms) / 1000.0
    return _ffprobe_duration(audio_path)


# ── ffmpeg helpers ────────────────────────────────────────────────────────────

def _run_ffmpeg(cmd: list[str], label: str) -> None:
    """Execute ffmpeg command; raise RuntimeError on non-zero exit."""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg 실패 ({label}):\n{result.stderr[-600:]}"
        )


def _mux_audio(
    video_path: Path,
    audio_path: Path,
    audio_dur: float,
    output_path: Path,
) -> None:
    """ffmpeg: copy video stream from Remotion MP4 + mux AAC audio → scene MP4."""
    cmd = [
        FFMPEG_BIN, "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", f"{audio_dur:.3f}",
        str(output_path),
    ]
    _run_ffmpeg(cmd, output_path.name)


def _render_static(
    slide_path: Path,
    audio_path: Path,
    audio_dur: float,
    output_path: Path,
) -> None:
    """ffmpeg: static PNG looped for audio_dur seconds + audio → MP4."""
    cmd = [
        FFMPEG_BIN, "-y",
        "-loop", "1",
        "-i", str(slide_path),
        "-i", str(audio_path),
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-pix_fmt", "yuv420p",
        "-r", str(VIDEO_FPS),
        "-t", f"{audio_dur:.3f}",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(output_path),
    ]
    _run_ffmpeg(cmd, output_path.name)


def _render_animated(
    animated_path: Path,
    audio_path: Path,
    audio_dur: float,
    output_path: Path,
) -> None:
    """ffmpeg: animated MP4 + audio → scene MP4 (last-frame hold if audio longer)."""
    cmd = [
        FFMPEG_BIN, "-y",
        "-i", str(animated_path),
        "-i", str(audio_path),
        "-filter_complex",
        f"[0:v]tpad=stop_mode=clone:stop_duration={audio_dur:.3f}[v]",
        "-map", "[v]",
        "-map", "1:a",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(VIDEO_FPS),
        "-t", f"{audio_dur:.3f}",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(output_path),
    ]
    _run_ffmpeg(cmd, output_path.name)


# ── Core API ──────────────────────────────────────────────────────────────────

def render_scene(
    scene: dict[str, Any],
    output_path: Path,
    *,
    force: bool = False,
) -> Path:
    """Render one scene to an MP4 file.

    Reads ``audio_path`` and ``slide_path`` from the scene dict.
    Updates scene in-place with ``render_path``, ``render_duration_frames``,
    and appends ``"render"`` to ``stages_done``.

    Args:
        scene:       Scene Object dict (v1 or v2 compatible).
        output_path: Destination .mp4 path.
        force:       Re-render even if output_path already exists.

    Returns:
        output_path on success.

    Raises:
        RuntimeError: Missing inputs or ffmpeg failure.
    """
    sid = scene.get("id", "?")

    # ── Cache check ────────────────────────────────────────────────────────────
    if output_path.exists() and not force:
        _log(f"씬 {sid}: skip (캐시 존재) → {output_path.name}", "warning")
        scene["render_path"] = str(output_path)
        if scene.get("render_duration_frames") is None:
            raw_audio = scene.get("audio_path") or ""
            dur = _resolve_duration(scene, Path(raw_audio))
            if dur is not None:
                scene["render_duration_frames"] = math.ceil(VIDEO_FPS * dur)
        stages_done: list[str] = list(scene.get("stages_done") or [])
        if "render" not in stages_done:
            stages_done.append("render")
        scene["stages_done"] = stages_done
        return output_path

    # ── Remotion 우선 렌더 시도 ─────────────────────────────────────────────────
    # hyperframe/ 디렉토리가 있을 때만 시도. 실패 시 PNG fallback으로 진행.
    _hyperframe_dir = Path(__file__).parent.parent / "hyperframe"
    if _hyperframe_dir.exists():
        _pipelines_dir = str(Path(__file__).parent)
        try:
            import sys as _sys
            if _pipelines_dir not in _sys.path:
                _sys.path.insert(0, _pipelines_dir)
            import render_template as _rt  # type: ignore[import]
            _fps = int(os.getenv("VIDEO_FPS", str(VIDEO_FPS)))
            _w = int(os.getenv("VIDEO_WIDTH", str(CANVAS_W)))
            _h = int(os.getenv("VIDEO_HEIGHT", str(CANVAS_H)))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            _video_only = output_path.with_name(output_path.stem + "_video_only.mp4")
            _rt.render_scene(scene, _video_only, fps=_fps, width=_w, height=_h, force=force)
            # Mux audio into Remotion video-only output
            _raw_audio = scene.get("audio_path") or ""
            _audio_p = Path(_raw_audio) if _raw_audio else None
            _dur = _resolve_duration(scene, _audio_p or Path(""))
            if _audio_p and _audio_p.exists() and _dur is not None:
                _mux_audio(_video_only, _audio_p, _dur, output_path)
                _video_only.unlink(missing_ok=True)
            else:
                _video_only.rename(output_path)
                _log(f"씬 {sid}: 오디오 없음 — video-only 출력", "warning")
            # Scene Object 업데이트
            scene["render_path"] = str(output_path)
            if _dur is not None:
                scene["render_duration_frames"] = math.ceil(VIDEO_FPS * _dur)
            _stages: list[str] = list(scene.get("stages_done") or [])
            if "render" not in _stages:
                _stages.append("render")
            scene["stages_done"] = _stages
            _log(f"씬 {sid}: Remotion 렌더 완료 → {output_path.name}", "success")
            return output_path
        except Exception as _exc:
            _log(f"씬 {sid}: Remotion 실패 → PNG fallback ({_exc})", "warning")

    # ── Resolve inputs ─────────────────────────────────────────────────────────
    raw_audio = scene.get("audio_path")
    raw_slide = scene.get("slide_path")

    if not raw_audio:
        raise RuntimeError(f"씬 {sid}: audio_path 필드 없음")
    if not raw_slide:
        raise RuntimeError(f"씬 {sid}: slide_path 필드 없음")

    audio_path = Path(raw_audio)
    slide_path = Path(raw_slide)

    if not audio_path.exists():
        raise RuntimeError(f"씬 {sid}: 오디오 파일 없음 → {audio_path}")
    if not slide_path.exists():
        raise RuntimeError(f"씬 {sid}: 슬라이드 파일 없음 → {slide_path}")

    # ── Resolve duration ───────────────────────────────────────────────────────
    audio_dur = _resolve_duration(scene, audio_path)
    if audio_dur is None:
        raise RuntimeError(
            f"씬 {sid}: 오디오 길이 결정 불가 "
            "(audio_duration_sec/ms 없고 ffprobe도 실패)"
        )

    duration_frames = math.ceil(VIDEO_FPS * audio_dur)

    # ── Animated MP4 variant check ─────────────────────────────────────────────
    animated_path = slide_path.parent / (slide_path.stem + "_animated.mp4")
    use_animated = animated_path.exists()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if use_animated:
        _log(f"씬 {sid}: animated MP4 사용 ({animated_path.name})")
        _render_animated(animated_path, audio_path, audio_dur, output_path)
    else:
        _log(f"씬 {sid}: 정지 PNG 사용 ({slide_path.name})")
        _render_static(slide_path, audio_path, audio_dur, output_path)

    # ── Update Scene Object ────────────────────────────────────────────────────
    scene["render_path"] = str(output_path)
    scene["render_duration_frames"] = duration_frames
    stages_done: list[str] = list(scene.get("stages_done") or [])
    if "render" not in stages_done:
        stages_done.append("render")
    scene["stages_done"] = stages_done

    _log(
        f"씬 {sid}: 완료 → {output_path.name} "
        f"({duration_frames}f / {audio_dur:.3f}s)",
        "success",
    )
    return output_path


def render_scenes(
    scenes: list[dict[str, Any]],
    scenes_dir: Path,
    *,
    force: bool = False,
) -> list[Path]:
    """Render all scenes to individual MP4 files in scenes_dir.

    Scenes are modified in-place (render_path, render_duration_frames).

    Args:
        scenes:     list of Scene Object dicts.
        scenes_dir: output directory for scene MP4 files.
        force:      re-render even if cached.

    Returns:
        list of successfully rendered MP4 paths.
    """
    scenes_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[Path] = []
    errors: list[str] = []

    for scene in scenes:
        sid = scene.get("id", 0)
        try:
            sid_int = int(sid)
            out = scenes_dir / f"scene{sid_int:02d}.mp4"
        except (ValueError, TypeError):
            out = scenes_dir / f"{sid}.mp4"

        try:
            path = render_scene(scene, out, force=force)
            rendered.append(path)
        except RuntimeError as exc:
            _log(f"씬 {sid} 렌더 실패: {exc}", "error")
            errors.append(str(exc))

    total = len(scenes)
    ok    = len(rendered)
    _log(
        f"render_scenes 완료 — {ok}/{total} 성공"
        + (f", {len(errors)}개 실패" if errors else ""),
        "success" if not errors else "warning",
    )
    return rendered


# ── CLI entry ─────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    p = argparse.ArgumentParser(
        prog="scene_render.py",
        description="S6-unit — Scene Object → scene_NN.mp4 per-scene renderer.",
    )
    p.add_argument(
        "--scenes-json", type=Path,
        default=WORK_DIR / "scenes.json",
        help="scenes.json 경로 (기본: work/scenes.json)",
    )
    p.add_argument(
        "--out-dir", type=Path,
        default=WORK_DIR / "scenes",
        help="씬 MP4 출력 디렉토리 (기본: work/scenes/)",
    )
    p.add_argument("--force",   action="store_true", help="캐시 무시, 재렌더")
    p.add_argument("--dry-run", action="store_true", help="입력 검증만 수행 (렌더 없음)")
    args = p.parse_args()

    if not args.scenes_json.exists():
        _log(f"scenes.json 없음: {args.scenes_json}", "error")
        sys.exit(1)

    data   = json.loads(args.scenes_json.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])

    if not scenes:
        _log("씬이 없습니다", "warning")
        sys.exit(0)

    if args.dry_run:
        _log(f"dry-run: {len(scenes)} 씬 입력 검증")
        for scene in scenes:
            sid   = scene.get("id", "?")
            audio = scene.get("audio_path", "MISSING")
            slide = scene.get("slide_path", "MISSING")
            dur   = scene.get("audio_duration_sec", "N/A")
            audio_ok = "OK" if Path(str(audio)).exists() else "MISSING"
            slide_ok = "OK" if Path(str(slide)).exists() else "MISSING"
            _log(f"  씬 {sid}: audio={audio_ok}, slide={slide_ok}, dur={dur}s")
        return

    render_scenes(scenes, args.out_dir, force=args.force)


if __name__ == "__main__":
    main()
