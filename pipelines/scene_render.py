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
    render_duration_frames  – total frames = ceil(FPS × (audio_duration_sec +
                              SCENE_TAIL_PADDING_SEC)); matches the physical
                              MP4 length (audio + hold/silence tail padding),
                              not the narration-only duration.
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
    from video_defaults import get_scene_tail_padding_sec  # type: ignore[import]
except ImportError:
    from pipelines.video_defaults import get_scene_tail_padding_sec  # type: ignore[no-redef]

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

# 씬 종료 시점 hold(정지 화면) + 무음 tail padding. 씬 전환 시 컷이 급작스럽지
# 않도록 각 sceneNN.mp4 끝에 부가된다. audio/sceneNN.mp3 원본이나 자막
# caption_segments(end_ms)는 영향받지 않는다 — 렌더 산출물에만 적용.
SCENE_TAIL_PADDING_SEC = get_scene_tail_padding_sec()


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


def _has_caption_segments(scene: dict[str, Any]) -> bool:
    """Return True when a scene carries real caption text that must not be lost."""
    segments = scene.get("caption_segments")
    if not isinstance(segments, list):
        return False
    for seg in segments:
        if isinstance(seg, dict) and str(seg.get("text") or "").strip():
            return True
    return False


def _is_template_validation_failure(exc: Exception) -> bool:
    text = str(exc)
    return (
        "retired_template_type:" in text
        or "Retired template type rejected" in text
        or "Unsupported template type" in text
    )


def _validate_scene_template(scene: dict[str, Any]) -> None:
    try:
        pipelines_dir = str(Path(__file__).parent)
        if pipelines_dir not in sys.path:
            sys.path.insert(0, pipelines_dir)
        from render_template import validate_template_type  # type: ignore[import]

        validate_template_type(scene.get("template_type"), scene_id=scene.get("id"))
    except Exception as exc:
        raise RuntimeError(f"scene template validation failed: {exc}") from exc


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
    *,
    padding_sec: float = SCENE_TAIL_PADDING_SEC,
) -> None:
    """ffmpeg: mux AAC audio into Remotion MP4 + append hold/silence tail padding.

    ``video_path`` (Remotion render) is exactly ``audio_dur`` long, so unlike
    the static/animated paths there is no natural over-provisioned hold
    buffer to lean on — ``-c:v copy`` cannot extend a stream, so this re-encodes
    with an explicit ``tpad`` clone of ``padding_sec`` at the tail. Audio gets
    the matching silence tail via ``apad``.
    """
    total_dur = audio_dur + padding_sec
    cmd = [
        FFMPEG_BIN, "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-filter_complex",
        f"[0:v]tpad=stop_mode=clone:stop_duration={padding_sec:.3f}[v]",
        "-map", "[v]",
        "-map", "1:a",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(VIDEO_FPS),
        "-af", f"apad=pad_dur={padding_sec:.3f}",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", f"{total_dur:.3f}",
        str(output_path),
    ]
    _run_ffmpeg(cmd, output_path.name)


def _render_static(
    slide_path: Path,
    audio_path: Path,
    audio_dur: float,
    output_path: Path,
    *,
    padding_sec: float = SCENE_TAIL_PADDING_SEC,
) -> None:
    """ffmpeg: static PNG looped for audio_dur+padding seconds + audio(+silence tail) → MP4."""
    total_dur = audio_dur + padding_sec
    cmd = [
        FFMPEG_BIN, "-y",
        "-loop", "1",
        "-i", str(slide_path),
        "-i", str(audio_path),
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-pix_fmt", "yuv420p",
        "-r", str(VIDEO_FPS),
        "-af", f"apad=pad_dur={padding_sec:.3f}",
        "-t", f"{total_dur:.3f}",
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
    *,
    padding_sec: float = SCENE_TAIL_PADDING_SEC,
) -> None:
    """ffmpeg: animated MP4 + audio → scene MP4 (last-frame hold covers audio_dur+padding)."""
    total_dur = audio_dur + padding_sec
    cmd = [
        FFMPEG_BIN, "-y",
        "-i", str(animated_path),
        "-i", str(audio_path),
        "-filter_complex",
        # stop_duration=total_dur over-provisions clone-hold frames by at
        # least total_dur regardless of the animated clip's own length, so
        # video stream length (animated_duration + total_dur) always exceeds
        # the -t target even for animated clips shorter than padding_sec —
        # -shortest can never truncate before total_dur is reached. The
        # exact output length is enforced below via -t.
        f"[0:v]tpad=stop_mode=clone:stop_duration={total_dur:.3f}[v]",
        "-map", "[v]",
        "-map", "1:a",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(VIDEO_FPS),
        "-af", f"apad=pad_dur={padding_sec:.3f}",
        "-t", f"{total_dur:.3f}",
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
    and appends ``"render"`` to ``stages_done``. ``render_duration_frames``
    reflects the physical output file's length, i.e. audio duration plus
    ``SCENE_TAIL_PADDING_SEC`` — it describes the rendered MP4, not the
    narration-only duration.

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
    _validate_scene_template(scene)

    # Resolve audio duration up front so a pre-existing output_path's actual
    # duration can be checked against the current padding policy before
    # deciding whether it's reusable.
    _raw_audio_for_cache = scene.get("audio_path") or ""
    _audio_dur_for_cache = (
        _resolve_duration(scene, Path(_raw_audio_for_cache)) if _raw_audio_for_cache else None
    )

    # ── Cache check ────────────────────────────────────────────────────────────
    effective_force = force
    if output_path.exists() and not force:
        cached_dur = _ffprobe_duration(output_path)
        cache_valid = True
        if _audio_dur_for_cache is not None:
            expected_dur = _audio_dur_for_cache + SCENE_TAIL_PADDING_SEC
            frame_tolerance_sec = 1.0 / VIDEO_FPS
            if cached_dur is None or abs(cached_dur - expected_dur) > frame_tolerance_sec:
                cache_valid = False
        # If audio duration can't be resolved at all, there's no padding
        # target to validate against — fall back to trusting the cache
        # (matches prior conservative behavior for that edge case only).

        if cache_valid:
            _log(f"씬 {sid}: skip (캐시 존재, padding 검증 통과) → {output_path.name}", "warning")
            scene["render_path"] = str(output_path)
            # Always overwrite with the freshly-probed/expected value, never
            # gate on "is None" — the scene dict may already carry a stale
            # pre-padding render_duration_frames (e.g. loaded from an older
            # scenes.json or an interrupted run), and since we've just
            # validated the cached MP4 itself is correctly padded, that
            # probed truth should always win over whatever was there before.
            if cached_dur is not None:
                scene["render_duration_frames"] = math.ceil(VIDEO_FPS * cached_dur)
            elif _audio_dur_for_cache is not None:
                scene["render_duration_frames"] = math.ceil(
                    VIDEO_FPS * (_audio_dur_for_cache + SCENE_TAIL_PADDING_SEC)
                )
            stages_done: list[str] = list(scene.get("stages_done") or [])
            if "render" not in stages_done:
                stages_done.append("render")
            scene["stages_done"] = stages_done
            return output_path

        # Cache invalid (missing/mismatched padding) — invalidate and fall
        # through to a full re-render below, overwriting output_path.
        # audio/sceneNN.mp3 (the TTS source) is never touched here.
        _log(
            f"씬 {sid}: 캐시 무효화 — 기존 mp4 길이"
            f"({'N/A' if cached_dur is None else f'{cached_dur:.3f}s'}) != "
            f"기대값({_audio_dur_for_cache + SCENE_TAIL_PADDING_SEC:.3f}s = "
            f"audio_dur+padding) → 재렌더",
            "warning",
        )
        effective_force = True

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
            _rt.render_scene(scene, _video_only, fps=_fps, width=_w, height=_h, force=effective_force)
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
                scene["render_duration_frames"] = math.ceil(
                    VIDEO_FPS * (_dur + SCENE_TAIL_PADDING_SEC)
                )
            _stages: list[str] = list(scene.get("stages_done") or [])
            if "render" not in _stages:
                _stages.append("render")
            scene["stages_done"] = _stages
            _log(f"씬 {sid}: Remotion 렌더 완료 → {output_path.name}", "success")
            return output_path
        except Exception as _exc:
            if _is_template_validation_failure(_exc):
                raise RuntimeError(
                    f"씬 {sid}: Remotion template validation 실패로 PNG fallback 금지 "
                    f"({_exc})"
                ) from _exc
            if _has_caption_segments(scene):
                raise RuntimeError(
                    f"씬 {sid}: Remotion 실패, caption_segments 존재로 PNG fallback 금지 "
                    f"({_exc})"
                ) from _exc
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

    duration_frames = math.ceil(VIDEO_FPS * (audio_dur + SCENE_TAIL_PADDING_SEC))

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

    # Validate the whole batch before writing scene outputs. This catches stale
    # worker artifacts that still contain retired/unsupported templates and
    # avoids producing a partial final video.
    try:
        pipelines_dir = str(Path(__file__).parent)
        if pipelines_dir not in sys.path:
            sys.path.insert(0, pipelines_dir)
        from render_template import validate_scene_templates  # type: ignore[import]

        validate_scene_templates(scenes)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"scene template pre-validation failed: {exc}") from exc

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
    if errors:
        raise RuntimeError(
            f"scene_render failed for {len(errors)}/{total} scenes:\n" + "\n".join(errors)
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
