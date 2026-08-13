"""Optional audio-based timing correction for narration-derived captions.

Whisper output is used only as a timing signal. The canonical caption text and
segment order remain the existing caption_segments produced from narration.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, TypedDict

try:
    from video_defaults import get_caption_whisper_lead_ms  # type: ignore[import]
except ImportError:
    from pipelines.video_defaults import get_caption_whisper_lead_ms  # type: ignore[no-redef]

log = logging.getLogger(__name__)

DEFAULT_MODE = "whisper"
DISABLE_VALUES = {"0", "false", "no", "off", "none", "skip", "disabled"}
LONG_SEGMENT_CHARS = 50
LONG_SEGMENT_MS = 4500
MIN_SEGMENT_MS = 1
DEFAULT_WHISPER_LEAD_MS = get_caption_whisper_lead_ms()


class AlignmentReport(TypedDict):
    total: int
    synced: int
    fallback: int
    skipped: int
    mode: str
    lead_ms: int
    scene_reports: list[dict[str, Any]]


def is_enabled() -> bool:
    """Return whether optional caption timing alignment should run."""
    raw = os.getenv("CAPTION_TIMING_ALIGN", DEFAULT_MODE).strip().lower()
    return raw not in DISABLE_VALUES


def _caption_whisper_lead_ms() -> int:
    """Configured caption lead for Whisper-SYNCED scenes only."""
    return get_caption_whisper_lead_ms()


def run_on_scenes(
    scenes_json: Path,
    audio_dir: Path | None = None,
    report_path: Path | None = None,
) -> AlignmentReport:
    """Align caption timing for all scenes in scenes_json.

    Text preservation is enforced per scene. If alignment is unavailable or
    produces unsafe timings, the original proportional timings are left intact.
    """
    data = json.loads(scenes_json.read_text(encoding="utf-8"))
    scenes: list[dict[str, Any]] = data if isinstance(data, list) else data.get("scenes", [])
    mode = os.getenv("CAPTION_TIMING_ALIGN", DEFAULT_MODE).strip().lower() or DEFAULT_MODE
    lead_ms = _caption_whisper_lead_ms()

    result: AlignmentReport = {
        "total": 0,
        "synced": 0,
        "fallback": 0,
        "skipped": 0,
        "mode": mode,
        "lead_ms": lead_ms,
        "scene_reports": [],
    }

    if not is_enabled():
        for scene in scenes:
            result["total"] += 1
            result["skipped"] += 1
            result["scene_reports"].append(
                _scene_report(scene, "SKIPPED", "CAPTION_TIMING_ALIGN disabled", 0, 0)
            )
        _write_report(report_path, result)
        return result

    for scene in scenes:
        result["total"] += 1
        report = align_scene(scene, audio_dir=audio_dir, lead_ms=lead_ms)
        result["scene_reports"].append(report)
        if report["status"] == "SYNCED":
            result["synced"] += 1
        elif report["status"] == "SKIPPED":
            result["skipped"] += 1
        else:
            result["fallback"] += 1

    if isinstance(data, list):
        out_data: Any = scenes
    else:
        data["scenes"] = scenes
        out_data = data

    scenes_json.write_text(json.dumps(out_data, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_report(report_path, result)
    return result


def align_scene(
    scene: dict[str, Any],
    audio_dir: Path | None = None,
    *,
    lead_ms: int | None = None,
) -> dict[str, Any]:
    """Apply timing correction to one scene, preserving text/order."""
    sid = scene.get("id", 0)
    original_segments = _caption_segments(scene)
    if not original_segments:
        return _scene_report(scene, "SKIPPED", "caption_segments empty", 0, 0)

    original_texts = [str(seg.get("text", "")) for seg in original_segments]
    audio_path = _resolve_audio_path(scene, audio_dir)
    if audio_path is None or not audio_path.exists():
        return _scene_report(scene, "FALLBACK", f"audio file missing for scene {sid}", 0, len(original_segments))

    audio_duration_ms = _audio_duration_ms(scene, original_segments)
    if audio_duration_ms <= 0:
        return _scene_report(scene, "FALLBACK", "audio_duration_ms unavailable", 0, len(original_segments))

    try:
        word_timestamps = _load_word_timestamps(audio_path, str(scene.get("narration", "")))
    except (Exception, SystemExit) as exc:  # whisper_align may call sys.exit on optional dependency failures.
        log.warning("caption_timing_align fallback for scene %s: %s", sid, exc)
        return _scene_report(
            scene,
            "FALLBACK",
            f"whisper unavailable or failed: {type(exc).__name__}: {exc}",
            0,
            len(original_segments),
        )

    if not word_timestamps:
        return _scene_report(scene, "FALLBACK", "word_timestamps empty", 0, len(original_segments))

    candidate = _allocate_by_speech_span(original_segments, word_timestamps, audio_duration_ms)
    effective_lead_ms = _caption_whisper_lead_ms() if lead_ms is None else max(0, int(lead_ms))
    if effective_lead_ms > 0:
        candidate = _apply_whisper_lead(candidate, effective_lead_ms, audio_duration_ms)
    validation_errors = validate_timing_segments(candidate, original_texts, audio_duration_ms)
    if validation_errors:
        return _scene_report(
            scene,
            "FALLBACK",
            "unsafe aligned timing: " + "; ".join(validation_errors[:3]),
            len(word_timestamps),
            len(original_segments),
        )

    scene["caption_segments"] = candidate
    scene["caption_source"] = scene.get("caption_source") or "direct"
    scene["caption_timing_source"] = "whisper_timing"
    scene["word_timestamps"] = word_timestamps
    return _scene_report(
        scene,
        "SYNCED",
        "timing corrected; caption text preserved",
        len(word_timestamps),
        len(candidate),
        lead_applied=effective_lead_ms > 0,
        lead_ms=effective_lead_ms if effective_lead_ms > 0 else 0,
    )


def validate_timing_segments(
    segments: list[dict[str, Any]],
    expected_texts: list[str] | None,
    audio_duration_ms: int,
) -> list[str]:
    """Validate text preservation, monotonic timing, overlaps, and long segments."""
    errors: list[str] = []
    if expected_texts is not None:
        actual_texts = [str(seg.get("text", "")) for seg in segments]
        if actual_texts != expected_texts:
            errors.append("caption text/order changed")

    prev_end = 0
    for idx, seg in enumerate(segments):
        start = int(seg.get("start_ms", -1))
        end = int(seg.get("end_ms", -1))
        text = str(seg.get("text", ""))
        if start < 0:
            errors.append(f"segment {idx}: negative start_ms")
        if end <= start:
            errors.append(f"segment {idx}: start_ms >= end_ms")
        if idx > 0 and start < prev_end:
            errors.append(f"segment {idx}: overlap with previous segment")
        if audio_duration_ms > 0 and end > audio_duration_ms:
            errors.append(f"segment {idx}: end_ms > audio_duration_ms")
        if len(text) > LONG_SEGMENT_CHARS or (end - start) > LONG_SEGMENT_MS:
            seg.setdefault("caption_timing_warning", "long_segment")
        prev_end = end
    return errors


def _load_word_timestamps(audio_path: Path, expected_text: str) -> list[dict[str, Any]]:
    if os.getenv("CAPTION_TIMING_ALIGN_FORCE_UNAVAILABLE", "").strip().lower() in {"1", "true", "yes"}:
        raise ImportError("forced unavailable by CAPTION_TIMING_ALIGN_FORCE_UNAVAILABLE")

    try:
        from whisper_align import align  # type: ignore[import]
    except ImportError:
        from pipelines.whisper_align import align  # type: ignore[no-redef]

    return list(align(audio_path, expected_text=expected_text))


def _allocate_by_speech_span(
    original_segments: list[dict[str, Any]],
    word_timestamps: list[dict[str, Any]],
    audio_duration_ms: int,
) -> list[dict[str, Any]]:
    valid_words = [
        wt for wt in word_timestamps
        if int(wt.get("end_ms", 0)) > int(wt.get("start_ms", 0))
    ]
    if not valid_words:
        return []

    speech_start = max(0, int(valid_words[0]["start_ms"]))
    speech_end = min(audio_duration_ms, int(valid_words[-1]["end_ms"]))
    if speech_end <= speech_start:
        return []

    total_chars = sum(max(1, len(str(seg.get("text", "")).strip())) for seg in original_segments)
    if (speech_end - speech_start) < len(original_segments):
        return []

    boundaries: list[int] = [speech_start]
    cursor = speech_start
    cumulative_chars = 0
    for idx, seg in enumerate(original_segments[:-1]):
        cumulative_chars += max(1, len(str(seg.get("text", "")).strip()))
        target = speech_start + round((speech_end - speech_start) * cumulative_chars / total_chars)
        remaining_segments = len(original_segments) - idx - 1
        min_end = cursor + 1
        max_end = speech_end - remaining_segments
        if max_end < min_end:
            return []
        cursor = max(min_end, min(target, max_end))
        boundaries.append(int(cursor))
    boundaries.append(speech_end)

    result: list[dict[str, Any]] = []
    for idx, seg in enumerate(original_segments):
        new_seg = dict(seg)
        start = 0 if idx == 0 else boundaries[idx]
        end = audio_duration_ms if idx == len(original_segments) - 1 else boundaries[idx + 1]
        if end <= start:
            end = min(audio_duration_ms, start + MIN_SEGMENT_MS)
        new_seg["start_ms"] = int(start)
        new_seg["end_ms"] = int(end)
        result.append(new_seg)

    return result


def _apply_whisper_lead(
    segments: list[dict[str, Any]],
    lead_ms: int,
    audio_duration_ms: int,
) -> list[dict[str, Any]]:
    """Shift Whisper-SYNCED caption timings earlier without changing text/order/count."""
    shifted: list[dict[str, Any]] = []
    prev_end = 0
    for seg in segments:
        new_seg = dict(seg)
        start = max(0, int(new_seg.get("start_ms", 0)) - lead_ms)
        end = int(new_seg.get("end_ms", 0)) - lead_ms
        if start < prev_end:
            start = prev_end
        if end <= start:
            end = start + MIN_SEGMENT_MS
        if audio_duration_ms > 0 and end > audio_duration_ms:
            end = audio_duration_ms
            if end <= start:
                start = max(0, end - MIN_SEGMENT_MS)
        new_seg["start_ms"] = int(start)
        new_seg["end_ms"] = int(end)
        shifted.append(new_seg)
        prev_end = int(end)
    return shifted


def _caption_segments(scene: dict[str, Any]) -> list[dict[str, Any]]:
    segs = scene.get("caption_segments") or []
    return [dict(seg) for seg in segs if isinstance(seg, dict)]


def _audio_duration_ms(scene: dict[str, Any], segs: list[dict[str, Any]]) -> int:
    raw = scene.get("audio_duration_ms")
    if isinstance(raw, (int, float)) and raw > 0:
        return int(raw)
    if segs:
        return int(segs[-1].get("end_ms", 0))
    return 0


def _resolve_audio_path(scene: dict[str, Any], audio_dir: Path | None) -> Path | None:
    if audio_dir is not None:
        sid = scene.get("id", 0)
        try:
            candidate = audio_dir / f"scene{int(sid):02d}.mp3"
            if candidate.exists():
                return candidate
        except (TypeError, ValueError):
            pass
    raw_path = scene.get("audio_path")
    if raw_path:
        return Path(str(raw_path))
    return None


def _scene_report(
    scene: dict[str, Any],
    status: str,
    reason: str,
    word_count: int,
    segment_count: int,
    *,
    lead_applied: bool = False,
    lead_ms: int = 0,
) -> dict[str, Any]:
    return {
        "scene_id": scene.get("id", 0),
        "status": status,
        "reason": reason,
        "word_count": word_count,
        "segment_count": segment_count,
        "lead_applied": lead_applied,
        "lead_ms": lead_ms,
    }


def _write_report(report_path: Path | None, result: AlignmentReport) -> None:
    if report_path is None:
        return
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Correct caption timing using optional Whisper timing signals.")
    parser.add_argument("scenes_json", type=Path)
    parser.add_argument("--audio-dir", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = run_on_scenes(args.scenes_json, audio_dir=args.audio_dir, report_path=args.report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
