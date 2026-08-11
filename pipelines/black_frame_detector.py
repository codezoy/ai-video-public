"""Black frame detection using ffmpeg blackdetect filter."""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

_SEGMENT_RE = re.compile(
    r"black_start:(?P<start>[\d.]+)\s+black_end:(?P<end>[\d.]+)\s+black_duration:(?P<duration>[\d.]+)"
)


def check(
    video_path: Path | str,
    *,
    min_duration: float = 0.2,
    pixel_threshold: float = 0.10,
    picture_black_ratio: float = 0.9999,
    ffmpeg_bin: str = "ffmpeg",
) -> dict:
    """Detect black frame segments in video_path.

    Segments shorter than min_duration are reported as WARNING.
    Any segment >= min_duration raises RuntimeError so HCHAIN can collect the cause.

    Returns:
        {
            "status": "PASS" | "WARNING" | "FAIL",
            "segments": [{"start": float, "end": float, "duration": float}, ...],
        }
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    cmd = [
        ffmpeg_bin,
        "-i", str(video_path),
        "-vf", f"blackdetect=d=0.1:pix_th={pixel_threshold:.2f}:pic_th={picture_black_ratio:.4f}",
        "-f", "null",
        "-",
    ]
    log.debug("blackdetect cmd: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    # blackdetect writes to stderr even on success
    combined = result.stderr + result.stdout

    segments: list[dict] = []
    for m in _SEGMENT_RE.finditer(combined):
        segments.append(
            {
                "start": float(m.group("start")),
                "end": float(m.group("end")),
                "duration": float(m.group("duration")),
            }
        )

    if not segments:
        log.info("blackdetect: PASS — no black segments found in %s", video_path.name)
        return {"status": "PASS", "segments": []}

    fail_segments = [s for s in segments if s["duration"] >= min_duration]
    warn_segments = [s for s in segments if s["duration"] < min_duration]

    if fail_segments:
        detail = "; ".join(
            f"t={s['start']:.2f}s–{s['end']:.2f}s ({s['duration']:.2f}s)"
            for s in fail_segments
        )
        log.error("blackdetect: FAIL — %d segment(s) >= %.1fs: %s", len(fail_segments), min_duration, detail)
        raise RuntimeError(
            f"Black frame detected in {video_path.name}: {len(fail_segments)} segment(s) >= {min_duration}s — {detail}"
        )

    log.warning(
        "blackdetect: WARNING — %d short segment(s) < %.1fs (ignored): %s",
        len(warn_segments),
        min_duration,
        "; ".join(f"{s['duration']:.2f}s@{s['start']:.2f}" for s in warn_segments),
    )
    return {"status": "WARNING", "segments": warn_segments}
