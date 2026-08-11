"""Opt-in publisher for exposing ai-video outputs to htube/NAS roots."""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ENV_PUBLISH_ROOT = "AIVIDEO_HTUBE_PUBLISH_ROOT"

_RUN_METADATA_FILENAMES = {
    "artifact_manifest.json",
    "scenes.json",
    "scene_quality_report.json",
    "qa_report.json",
    "quality_report.json",
    "mode_audit.json",
}


@dataclass(frozen=True)
class PublishResult:
    publish_root: Path
    destination_dir: Path
    video_path: Path
    metadata_path: Path
    copied_files: tuple[Path, ...]


def safe_path_component(value: str | None, fallback: str) -> str:
    """Return a single filesystem component with traversal characters removed."""
    text = (value or "").strip()
    if not text:
        text = fallback
    text = text.replace("/", "-").replace("\\", "-")
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^\w.-]+", "-", text, flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("._-")
    text = "-".join(part for part in text.split("-") if part not in {".", ".."})
    if not text or text in {".", ".."}:
        text = fallback
    if text in {".", ".."}:
        text = "untitled"
    return text[:120]


def publish_from_env(
    *,
    run_id: str,
    topic: str,
    run_dir: str | Path,
    final_mp4_path: str | Path,
) -> PublishResult | None:
    publish_root = os.getenv(ENV_PUBLISH_ROOT, "").strip()
    if not publish_root:
        return None
    return publish_run_output(
        publish_root=Path(publish_root),
        run_id=run_id,
        topic=topic,
        run_dir=Path(run_dir),
        final_mp4_path=Path(final_mp4_path),
    )


def publish_run_output(
    *,
    publish_root: Path,
    run_id: str,
    topic: str,
    run_dir: Path,
    final_mp4_path: Path,
) -> PublishResult:
    if not final_mp4_path.exists() or not final_mp4_path.is_file():
        raise FileNotFoundError(f"final MP4 not found: {final_mp4_path}")

    safe_topic = safe_path_component(topic, "untitled")
    safe_run_id = safe_path_component(run_id, "run")

    root = publish_root.expanduser()
    destination_dir = root / safe_topic / safe_run_id
    destination_dir.mkdir(parents=True, exist_ok=True)

    resolved_root = root.resolve()
    resolved_destination = destination_dir.resolve()
    if not resolved_destination.is_relative_to(resolved_root):
        raise ValueError(f"publish destination escaped root: {destination_dir}")

    copied_files: list[Path] = []
    video_dest = destination_dir / "video.mp4"
    _copy_file_atomic(final_mp4_path, video_dest)
    copied_files.append(video_dest)

    for source in _iter_run_metadata_files(run_dir):
        dest = destination_dir / source.name
        _copy_file_atomic(source, dest)
        copied_files.append(dest)

    metadata_dest = destination_dir / "publish_metadata.json"
    published_at = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
    metadata = {
        "run_id": run_id,
        "safe_run_id": safe_run_id,
        "topic": topic,
        "safe_topic": safe_topic,
        "published_at": published_at,
        "source_final_mp4_path": str(final_mp4_path),
        "source_run_dir": str(run_dir),
        "publish_root": str(root),
        "destination_dir": str(destination_dir),
        "copied_files": [p.name for p in copied_files],
    }
    _write_json_atomic(metadata_dest, metadata)
    copied_files.append(metadata_dest)

    return PublishResult(
        publish_root=root,
        destination_dir=destination_dir,
        video_path=video_dest,
        metadata_path=metadata_dest,
        copied_files=tuple(copied_files),
    )


def _iter_run_metadata_files(run_dir: Path) -> Iterable[Path]:
    if not run_dir.exists():
        return ()

    selected: list[Path] = []
    for name in sorted(_RUN_METADATA_FILENAMES):
        candidate = run_dir / name
        if candidate.is_file():
            selected.append(candidate)
    for candidate in sorted(run_dir.glob("*.log")):
        if candidate.is_file():
            selected.append(candidate)
    return selected


def _copy_file_atomic(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    try:
        with src.open("rb") as in_f, tmp.open("xb") as out_f:
            shutil.copyfileobj(in_f, out_f, length=1024 * 1024)
            out_f.flush()
            os.fsync(out_f.fileno())
        shutil.copystat(src, tmp)
        os.replace(tmp, dst)
        _fsync_dir(dst.parent)
    finally:
        if tmp.exists():
            tmp.unlink()


def _write_json_atomic(dst: Path, data: dict) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    try:
        with tmp.open("x", encoding="utf-8") as out_f:
            json.dump(data, out_f, ensure_ascii=False, indent=2)
            out_f.write("\n")
            out_f.flush()
            os.fsync(out_f.fileno())
        os.replace(tmp, dst)
        _fsync_dir(dst.parent)
    finally:
        if tmp.exists():
            tmp.unlink()


def _fsync_dir(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        return
    finally:
        os.close(fd)
