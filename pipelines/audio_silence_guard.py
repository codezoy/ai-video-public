"""Audio silence trimming guard.

- Leading / trailing silence: 완전 제거
- Middle silence ≥ SILENCE_THRESHOLD_SEC(1.0s): SILENCE_KEEP_SEC(0.2s)로 단축
- duration=0 파일: WARNING 로그 후 원본 경로 반환 (caller가 retry 결정)
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

_NOISE_DB: float = float(os.getenv("SILENCE_NOISE_DB", "-45"))
_SILENCE_THRESHOLD_SEC: float = float(os.getenv("SILENCE_THRESHOLD_SEC", "1.0"))
_SILENCE_KEEP_SEC: float = float(os.getenv("SILENCE_KEEP_SEC", "0.2"))
_DETECT_MIN_DUR: float = 0.05
_EDGE_TOL: float = 0.05


def _ffmpeg() -> str:
    return os.getenv("FFMPEG_BIN", "ffmpeg")


def _get_duration(path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except (ValueError, subprocess.TimeoutExpired):
        return 0.0


def _detect_silences(path: Path) -> list[tuple[float, float]]:
    """silencedetect로 무음 구간 목록을 반환한다. [(start, end), ...]"""
    af = f"silencedetect=noise={_NOISE_DB}dB:d={_DETECT_MIN_DUR}"
    cmd = [_ffmpeg(), "-i", str(path), "-af", af, "-f", "null", "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        log.warning("[audio_silence_guard] silencedetect timeout: %s", path.name)
        return []

    _num = r"[-+]?[\d.]+(?:[eE][-+]?\d+)?"
    starts = [float(x) for x in re.findall(rf"silence_start: ({_num})", r.stderr)]
    ends = [float(x) for x in re.findall(rf"silence_end: ({_num})", r.stderr)]

    silences: list[tuple[float, float]] = list(zip(starts, ends))
    if len(starts) > len(ends):
        silences.append((starts[-1], float("inf")))
    return silences


def trim_silence(mp3_path: Path) -> Path:
    """Leading/trailing 무음을 제거하고 middle 무음을 단축한다.

    파일을 in-place로 수정한다 (temp 파일 교체).
    수정 불필요하거나 실패 시 원본 경로를 반환한다.
    """
    if not mp3_path.exists() or mp3_path.stat().st_size == 0:
        log.warning("[audio_silence_guard] 파일 없거나 크기=0: %s", mp3_path.name)
        return mp3_path

    total_dur = _get_duration(mp3_path)
    if total_dur <= 0:
        log.warning("[audio_silence_guard] duration=0 탐지: %s", mp3_path.name)
        return mp3_path

    silences = _detect_silences(mp3_path)
    if not silences:
        return mp3_path

    # inf → total_dur
    silences = [(s, min(e, total_dur)) for s, e in silences]

    leading_end = 0.0
    trailing_start = total_dur
    middle_long: list[tuple[float, float]] = []

    for s_start, s_end in silences:
        dur = s_end - s_start
        if s_start <= _EDGE_TOL:
            leading_end = max(leading_end, s_end)
        elif s_end >= total_dur - _EDGE_TOL:
            trailing_start = min(trailing_start, s_start)
        elif dur >= _SILENCE_THRESHOLD_SEC:
            middle_long.append((s_start, s_end))

    has_leading = leading_end > _EDGE_TOL
    has_trailing = trailing_start < total_dur - _EDGE_TOL
    has_middle = bool(middle_long)

    if not has_leading and not has_trailing and not has_middle:
        return mp3_path

    content_start = leading_end if has_leading else 0.0
    content_end = trailing_start if has_trailing else total_dur

    if content_start >= content_end:
        log.warning("[audio_silence_guard] 콘텐츠 범위 없음 (무음만 존재): %s", mp3_path.name)
        return mp3_path

    # 유지할 구간 목록 구성
    keep: list[tuple[float, float]] = []
    prev = content_start

    for ms, me in sorted(middle_long, key=lambda x: x[0]):
        if ms <= prev:
            continue
        if ms > prev:
            keep.append((prev, ms))
        silence_keep_end = min(ms + _SILENCE_KEEP_SEC, me)
        keep.append((ms, silence_keep_end))
        prev = me

    if prev < content_end:
        keep.append((prev, content_end))

    if not keep:
        log.warning("[audio_silence_guard] keep segments empty: %s", mp3_path.name)
        return mp3_path

    # 단일 구간이며 변경 없음 → 스킵
    if (
        len(keep) == 1
        and not has_leading
        and not has_trailing
        and abs(keep[0][0] - content_start) < 0.01
        and abs(keep[0][1] - content_end) < 0.01
    ):
        return mp3_path

    # filter_complex 구성
    n = len(keep)
    filter_parts: list[str] = []
    for i, (seg_s, seg_e) in enumerate(keep):
        filter_parts.append(
            f"[0:a]atrim={seg_s:.4f}:{seg_e:.4f},asetpts=PTS-STARTPTS[s{i}]"
        )
    concat_inputs = "".join(f"[s{i}]" for i in range(n))
    filter_parts.append(f"{concat_inputs}concat=n={n}:v=0:a=1[out]")
    filter_complex = ";".join(filter_parts)

    suffix = mp3_path.suffix
    tmp_fd, tmp_name = tempfile.mkstemp(suffix=suffix, dir=str(mp3_path.parent))
    os.close(tmp_fd)
    tmp_path = Path(tmp_name)

    try:
        cmd = [
            _ffmpeg(), "-y", "-i", str(mp3_path),
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-c:a", "libmp3lame", "-q:a", "4",
            str(tmp_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            log.warning(
                "[audio_silence_guard] ffmpeg 실패 (%s): %s",
                mp3_path.name,
                r.stderr[-400:],
            )
            return mp3_path

        out_dur = _get_duration(tmp_path)
        if out_dur <= 0:
            log.warning("[audio_silence_guard] 출력 duration=0: %s", mp3_path.name)
            return mp3_path

        tmp_path.replace(mp3_path)
        log.info(
            "[audio_silence_guard] trim 완료 %.2fs → %.2fs: %s",
            total_dur,
            out_dur,
            mp3_path.name,
        )
        return mp3_path

    except subprocess.TimeoutExpired:
        log.warning("[audio_silence_guard] ffmpeg timeout: %s", mp3_path.name)
        return mp3_path
    except Exception as exc:
        log.warning("[audio_silence_guard] 예외 (%s): %s", mp3_path.name, exc)
        return mp3_path
    finally:
        tmp_path.unlink(missing_ok=True)
