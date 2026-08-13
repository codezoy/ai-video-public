"""Run endpoints — artifact, cancel, logs, enhanced detail."""
from __future__ import annotations

import datetime
import json
import logging
import os
import re
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.background import BackgroundTask

from api.schemas.run_request import RunCreateRequest
from api.schemas.run_response import (
    BulkDeleteTestRunsResponse,
    RunAvailableArtifactResponse,
    RunArtifactListResponse,
    RunArtifactResponse,
    RunCancelResponse,
    RunDeleteResponse,
    RunListResponse,
    RunLogEntry,
    RunLogsResponse,
    RunResponse,
    RunStageProgressResponse,
    RunStageResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/runs", tags=["Runs"])

_cancel_events: dict[str, threading.Event] = {}
_active_run_ids: set[str] = set()
_lifecycle_lock = threading.Lock()


def register_external_run(run_id: str, cancel_event: threading.Event) -> None:
    """Register a worker-managed run so cancel signals and stale cleanup work."""
    with _lifecycle_lock:
        _cancel_events[run_id] = cancel_event
        _active_run_ids.add(run_id)


def unregister_external_run(run_id: str) -> None:
    """Unregister a worker-managed run after it completes or fails."""
    with _lifecycle_lock:
        _cancel_events.pop(run_id, None)
        _active_run_ids.discard(run_id)

_KNOWN_STAGES = [
    "script", "polish", "scenes", "scene_quality", "tts",
    "whisper_align", "caption_segment", "caption_validate",
    "motion_anchor", "render", "concat", "qa",
]

_RUNS_ROOT = (Path(__file__).resolve().parent.parent.parent / "work" / "runs").resolve()


def _run_dir(run_id: str) -> Path | None:
    candidate = (_RUNS_ROOT / run_id).resolve()
    if not candidate.is_relative_to(_RUNS_ROOT):
        return None
    return candidate


def _download_name(value: str, fallback: str) -> str:
    return re.sub(r'[/\\:*?"<>|]', "_", value.strip()).strip("_") or fallback


def _api_time(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=datetime.timezone.utc)
        return value.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def _available_artifacts(row: Any) -> list[RunAvailableArtifactResponse]:
    run_id = row["run_id"]
    run_dir = _run_dir(run_id)
    if not run_dir or not run_dir.is_dir():
        return []

    keys = row.keys() if hasattr(row, "keys") else []
    contents = row["contents"] if "contents" in keys else None
    artifacts: list[RunAvailableArtifactResponse] = []
    script_path = next((p for p in (run_dir / "scripts" / "script.md", run_dir / "script.md") if p.is_file()), None)
    if script_path or contents:
        artifacts.append(RunAvailableArtifactResponse(
            key="script", name="Source Content", filename="source.md",
            size_bytes=script_path.stat().st_size if script_path else len(contents.encode("utf-8")),
            download_url=f"/runs/{run_id}/artifacts/script/download",
        ))

    scenes_path = run_dir / "scenes.json"
    if scenes_path.is_file() and scenes_path.stat().st_size > 0:
        artifacts.append(RunAvailableArtifactResponse(
            key="scenes", name="Scene JSON", filename="scenes.json",
            size_bytes=scenes_path.stat().st_size,
            download_url=f"/runs/{run_id}/artifacts/scenes/download",
        ))

    audio_files = sorted(p for p in (run_dir / "audio").glob("scene*.mp3") if p.stat().st_size > 0)
    if audio_files:
        artifacts.append(RunAvailableArtifactResponse(
            key="audio", name="Voiceover", filename="voiceover-mp3.zip",
            size_bytes=sum(p.stat().st_size for p in audio_files), file_count=len(audio_files),
            download_url=f"/runs/{run_id}/artifacts/audio/download",
        ))

    final_path_value = row["final_mp4_path"] if "final_mp4_path" in keys else None
    final_path = Path(final_path_value) if final_path_value else run_dir / "video.mp4"
    if final_path.is_file() and final_path.stat().st_size > 0:
        artifacts.append(RunAvailableArtifactResponse(
            key="video", name="Final video", filename="video.mp4",
            size_bytes=final_path.stat().st_size,
            download_url=f"/runs/{run_id}/artifacts/video/download",
        ))
    return artifacts


def _compute_progress(stages: list[Any], run_status: str = "") -> float | None:
    if run_status == "DONE":
        return 100.0
    done = sum(1 for s in stages if s["status"] in ("DONE", "SKIP", "PASS"))
    if not stages:
        return None
    return round(done / len(_KNOWN_STAGES) * 100, 1)


def _current_stage(stages: list[Any]) -> str | None:
    running = [s for s in stages if s["status"] == "RUNNING"]
    if running:
        return running[-1]["stage_key"]
    done = [s for s in stages if s["status"] in ("DONE", "SKIP")]
    if done:
        return done[-1]["stage_key"]
    return None


def _live_stage_progress(run_id: str, run_status: str) -> RunStageProgressResponse | None:
    """Read lightweight, file-backed progress for long stages not updated in DB until completion."""
    if run_status != "RUNNING":
        return None

    run_dir = _run_dir(run_id)
    if not run_dir or not run_dir.is_dir():
        return None

    scenes_path = run_dir / "scenes.json"
    if not scenes_path.is_file() or (run_dir / "stage_tts.done").exists():
        return None

    try:
        scenes = json.loads(scenes_path.read_text(encoding="utf-8")).get("scenes", [])
        total = len(scenes)
    except (OSError, ValueError, AttributeError):
        return None
    if total <= 0:
        return None

    audio_files = [p for p in (run_dir / "audio").glob("scene*.mp3") if p.stat().st_size > 0]
    completed = min(len(audio_files), total)
    latest_mtime = max((p.stat().st_mtime for p in audio_files), default=scenes_path.stat().st_mtime)
    updated_at = datetime.datetime.fromtimestamp(latest_mtime, datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    return RunStageProgressResponse(
        stage_key="tts",
        label="Audio Generation",
        completed=completed,
        total=total,
        percent=round(completed / total * 100),
        updated_at=updated_at,
    )


def _row_to_run(
    row: Any,
    stages: list[Any],
    scene_count: int | None = None,
    artifact_count: int | None = None,
) -> RunResponse:
    stage_list = [
        RunStageResponse(
            stage_key=s["stage_key"],
            status=s["status"],
            started_at=_api_time(s["started_at"]),
            completed_at=_api_time(s["completed_at"]),
            duration_sec=s["duration_sec"],
            error_msg=s["error_msg"] or None,
        )
        for s in stages
    ]

    duration_sec: float | None = None
    if row["started_at"] and row["completed_at"]:
        try:
            started_value = row["started_at"]
            completed_value = row["completed_at"]
            started = (
                started_value
                if isinstance(started_value, datetime.datetime)
                else datetime.datetime.fromisoformat(str(started_value).rstrip("Z"))
            )
            completed = (
                completed_value
                if isinstance(completed_value, datetime.datetime)
                else datetime.datetime.fromisoformat(str(completed_value).rstrip("Z"))
            )
            duration_sec = (completed - started).total_seconds()
        except Exception:
            pass

    keys = row.keys() if hasattr(row, "keys") else []
    language = row["language"] if "language" in keys else "ko"
    contents = row["contents"] if "contents" in keys else None
    target_duration_sec = row["target_duration_sec"] if "target_duration_sec" in keys else None
    mode = row["mode"] if "mode" in keys else None
    prompt_filename = row["prompt_filename"] if "prompt_filename" in keys else None
    video_template = row["video_template"] if "video_template" in keys else None
    video_templates_used = row["video_templates_used"] if "video_templates_used" in keys else None
    run_type = row["run_type"] if "run_type" in keys else "TEST"
    tts_provider = row["tts_provider"] if "tts_provider" in keys else "azure"
    tts_voice = row["tts_voice"] if "tts_voice" in keys else None
    tts_fallback_used = bool(row["tts_fallback_used"]) if "tts_fallback_used" in keys and row["tts_fallback_used"] is not None else False
    tts_audio_duration_sec = row["tts_audio_duration_sec"] if "tts_audio_duration_sec" in keys and row["tts_audio_duration_sec"] is not None else None
    tts_stage = next((s for s in stages if s["stage_key"] == "tts"), None)
    tts_cache_used = (
        bool(row["tts_cache_used"])
        if tts_stage and tts_stage["status"] in ("DONE", "PASS", "FAIL")
        and "tts_cache_used" in keys and row["tts_cache_used"] is not None
        else None
    )

    live_progress = _live_stage_progress(row["run_id"], row["status"])
    if not scene_count and live_progress:
        scene_count = live_progress.total

    queue_position: int | None = None
    if row["status"] == "QUEUED":
        try:
            from db import ops as _db_ops_qp
            queue_position = _db_ops_qp.get_queue_position(row["run_id"])
        except Exception:
            pass

    return RunResponse(
        run_id=row["run_id"],
        topic=row["topic"],
        profile_name=row["profile_name"] or None,
        language=language or "ko",
        status=row["status"],
        started_at=_api_time(row["started_at"]),
        completed_at=_api_time(row["completed_at"]),
        selected_input_path=row["selected_input_path"] or None,
        work_dir=row["work_dir"] or None,
        final_mp4_path=row["final_mp4_path"] or None,
        stages=stage_list,
        scene_count=scene_count,
        duration_sec=duration_sec,
        artifact_count=artifact_count,
        current_stage=_current_stage(stages),
        progress_percent=_compute_progress(stages, row["status"]),
        stage_progress=live_progress,
        available_artifacts=_available_artifacts(row),
        contents=contents or None,
        target_duration_sec=int(target_duration_sec) if target_duration_sec else None,
        mode=mode or None,
        prompt_filename=prompt_filename or None,
        video_template=video_template or None,
        video_templates_used=video_templates_used or None,
        run_type=run_type or "TEST",
        tts_provider=tts_provider or "azure",
        tts_voice=tts_voice or None,
        tts_fallback_used=tts_fallback_used,
        tts_audio_duration_sec=tts_audio_duration_sec,
        tts_cache_used=tts_cache_used,
        queue_position=queue_position,
    )


@router.get(
    "",
    response_model=RunListResponse,
    responses={500: {"description": "Internal server error"}},
)
def list_runs(limit: int = 20, offset: int = 0, run_type: str | None = None) -> RunListResponse:
    from db import ops as _db_ops
    from db.connection import get_connection

    with _lifecycle_lock:
        exclude_ids = _active_run_ids.copy()
    _db_ops.mark_stale_runs_failed(exclude_run_ids=exclude_ids)
    conn = get_connection()
    try:
        if run_type:
            rows = conn.execute(
                "SELECT * FROM runs WHERE run_type = %s ORDER BY started_at DESC LIMIT %s OFFSET %s",
                (run_type, limit, offset),
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) FROM runs WHERE run_type = %s", (run_type,)).fetchone()[0]
        else:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT %s OFFSET %s",
                (limit, offset),
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

        runs = []
        for row in rows:
            stages = conn.execute(
                "SELECT * FROM run_stages WHERE run_id = %s ORDER BY started_at",
                (row["run_id"],),
            ).fetchall()
            artifact_count = conn.execute(
                "SELECT COUNT(*) FROM run_artifacts WHERE run_id = %s",
                (row["run_id"],),
            ).fetchone()[0]
            scene_count = conn.execute(
                "SELECT COUNT(*) FROM run_scene_plans WHERE run_id = %s",
                (row["run_id"],),
            ).fetchone()[0] or None
            runs.append(_row_to_run(row, stages, scene_count, artifact_count))
    finally:
        conn.close()

    return RunListResponse(runs=runs, total=total)


@router.get(
    "/{run_id}",
    response_model=RunResponse,
    responses={
        404: {"description": "Run not found"},
        500: {"description": "Internal server error"},
    },
)
def get_run(run_id: str) -> RunResponse:
    from db.connection import get_connection

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM runs WHERE run_id = %s", (run_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        stages = conn.execute(
            "SELECT * FROM run_stages WHERE run_id = %s ORDER BY started_at",
            (run_id,),
        ).fetchall()
        artifact_count = conn.execute(
            "SELECT COUNT(*) FROM run_artifacts WHERE run_id = %s",
            (run_id,),
        ).fetchone()[0]
        scene_count = conn.execute(
            "SELECT COUNT(*) FROM run_scene_plans WHERE run_id = %s",
            (run_id,),
        ).fetchone()[0] or None
        result = _row_to_run(row, stages, scene_count, artifact_count)
    finally:
        conn.close()

    return result


_FULL_TERMINAL_STAGES = {"qa"}


def _resolve_stop_artifact(run_id: str, stop_after: str) -> str:
    from pathlib import Path
    proj_root = Path(__file__).resolve().parent.parent.parent
    run_dir = proj_root / "work" / "runs" / run_id
    candidates = {
        "script": run_dir / "scripts" / "script.md",
        "polish": run_dir / "scripts" / "script.md",
        "tts": run_dir / "narration",
        "render": run_dir / "slides",
        "concat": run_dir / "video",
    }
    p = candidates.get(stop_after)
    if p and p.exists():
        return str(p)
    return ""


def _run_pipeline_bg(request: RunCreateRequest, run_id: str, cancel_event: threading.Event) -> None:
    from api.services.run_service import RunService

    with _lifecycle_lock:
        _active_run_ids.add(run_id)
    svc = RunService()
    try:
        svc.run_video_pipeline(
            topic=request.topic,
            input_path=request.input_path,
            stop_after=request.stop_after,
            dry_run=request.dry_run,
            force=request.force,
            iteration=request.iteration,
            auto_correct=request.auto_correct,
            target_duration_sec=request.target_duration_sec,
            mode=request.mode,
            run_id=run_id,
            language=request.language,
            contents=request.contents,
            prompt_filename=request.prompt_filename,
            tts_provider=request.tts_provider,
            tts_voice=request.tts_voice,
            cancel_event=cancel_event,
        )
        if cancel_event.is_set():
            pass  # pipeline already marked CANCELLED internally
        elif request.stop_after not in _FULL_TERMINAL_STAGES:
            try:
                from db import ops as _db_ops
                stop_key = request.stop_after.upper().replace("-", "_")
                out_file = _resolve_stop_artifact(run_id, request.stop_after)
                _db_ops.complete_run(run_id, out_file, status=f"STOPPED_AFTER_{stop_key}")
            except Exception as e:
                logger.warning("[runs] Could not mark partial run complete: %s", e)
    except BaseException as exc:
        logger.error("[runs] Background pipeline failed: %s", exc)
        try:
            from db import ops as _db_ops
            _db_ops.complete_run(run_id, status="FAILED")
        except Exception:
            pass
    finally:
        with _lifecycle_lock:
            _active_run_ids.discard(run_id)
            _cancel_events.pop(run_id, None)


@router.post(
    "",
    status_code=202,
    responses={
        422: {"description": "Validation error"},
        500: {"description": "Internal server error"},
    },
)
def create_run(
    request: RunCreateRequest,
) -> dict:
    from api.services.tts_settings import PRODUCTION_TTS_PROVIDERS, resolve_tts

    try:
        resolved_provider, resolved_voice = resolve_tts(request.tts_provider, request.tts_voice)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if request.run_type == "PRODUCTION" and resolved_provider not in PRODUCTION_TTS_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"TTS provider '{resolved_provider}' is TEST-only; PRODUCTION allows {sorted(PRODUCTION_TTS_PROVIDERS)}",
        )
    request.tts_provider = resolved_provider
    request.tts_voice = resolved_voice

    import re
    run_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    _safe_topic = re.sub(r'[^\w가-힣ㄱ-ㅎㅏ-ㅣ\-]', '_', request.topic)[:80].strip('_')
    run_id = f"{_safe_topic}_{request.language}_{run_ts}"

    queue_position = None
    try:
        from db import ops as _db_ops
        from pipelines.generation_profiles import select_profile
        _db_ops.init()
        _profile_name, _ = select_profile(request.target_duration_sec or 120)
        _db_ops.create_run(
            run_id, request.topic, request.input_path, "",
            profile_name=_profile_name, language=request.language,
            contents=request.contents,
            target_duration_sec=request.target_duration_sec,
            mode=request.mode,
            prompt_filename=request.prompt_filename,
            run_type=request.run_type,
            tts_provider=request.tts_provider,
            tts_voice=request.tts_voice,
        )
        queue_position = _db_ops.get_queue_position(run_id)
    except Exception as exc:
        logger.error("[runs] DB pre-create failed: %s", exc)
        raise HTTPException(status_code=500, detail="Database is unavailable") from exc

    return {"status": "queued", "run_id": run_id, "topic": request.topic, "language": request.language, "queue_position": queue_position}


@router.post(
    "/{run_id}/cancel",
    response_model=RunCancelResponse,
    responses={
        404: {"description": "Run not found"},
        500: {"description": "Internal server error"},
    },
)
def cancel_run(run_id: str) -> RunCancelResponse:
    from db.connection import get_connection
    from db import ops as _db_ops

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT run_id, status FROM runs WHERE run_id = %s", (run_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        current_status = row["status"]
    finally:
        conn.close()

    with _lifecycle_lock:
        event = _cancel_events.get(run_id)
    if event:
        event.set()
        logger.info("[runs] cancel_event.set() for run_id=%s", run_id)
    cancelled = _db_ops.cancel_run(run_id)

    conn2 = get_connection()
    try:
        updated = conn2.execute(
            "SELECT status FROM runs WHERE run_id = %s", (run_id,)
        ).fetchone()
        new_status = updated["status"] if updated else current_status
    finally:
        conn2.close()

    return RunCancelResponse(run_id=run_id, status=new_status, cancelled=cancelled)


@router.post(
    "/{run_id}/resume",
    responses={
        400: {"description": "Run not in resumable state (must be FAILED or CANCELLED)"},
        404: {"description": "Run not found"},
    },
)
def resume_run(run_id: str) -> dict[str, str]:
    """Re-queue a FAILED or CANCELLED run for execution by the queue worker.

    Before re-queuing:
    - If all TTS audio files exist but stage_tts.done is missing, it is auto-created.
    - When the worker picks it up, force=False so completed stages are skipped.
    """
    from db import ops as _db_ops
    from db.connection import get_connection
    import json as _json

    # 1. Read current run state
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM runs WHERE run_id = %s", (run_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        current_status = row["status"]
        row_dict = dict(row)
    finally:
        conn.close()

    if current_status not in ("FAILED", "CANCELLED"):
        raise HTTPException(
            status_code=400,
            detail=f"Run status is '{current_status}'; only FAILED or CANCELLED runs can be resumed",
        )

    # 2. Auto-repair stage_tts.done if all audio files are present
    run_dir = _run_dir(run_id)
    _tts_repaired = False
    if run_dir and run_dir.is_dir():
        tts_done_flag = run_dir / "stage_tts.done"
        if not tts_done_flag.exists():
            audio_dir = run_dir / "audio"
            scenes_json_path = run_dir / "scenes.json"
            if audio_dir.is_dir() and scenes_json_path.exists():
                try:
                    _data = _json.loads(scenes_json_path.read_text(encoding="utf-8"))
                    _expected = len(_data.get("scenes", []))
                    _mp3s = [p for p in audio_dir.glob("scene*.mp3") if p.stat().st_size > 0]
                    if _expected > 0 and len(_mp3s) >= _expected:
                        tts_done_flag.touch()
                        _tts_repaired = True
                        logger.info(
                            "[resume] stage_tts.done 자동 생성 run_id=%s files=%d/%d",
                            run_id, len(_mp3s), _expected,
                        )
                except Exception as _e:
                    logger.warning("[resume] TTS artifact 검사 실패 (무시): %s", _e)

    # 3. Guard against concurrent resume of the same run
    with _lifecycle_lock:
        if run_id in _cancel_events:
            raise HTTPException(
                status_code=409,
                detail=f"Run {run_id} is already active. Cancel it first.",
            )

    # 4. Reset DB status to QUEUED — worker will pick it up
    if _db_ops.resume_run(run_id) is None:
        raise HTTPException(status_code=500, detail="Failed to update run status in database.")

    return {
        "status": "queued",
        "run_id": run_id,
        "resumed_from": current_status,
        "tts_repaired": str(_tts_repaired),
    }


@router.delete(
    "/bulk-test",
    response_model=BulkDeleteTestRunsResponse,
    responses={500: {"description": "Internal server error"}},
)
def bulk_delete_test_runs() -> BulkDeleteTestRunsResponse:
    from db import ops as _db_ops

    result = _db_ops.bulk_delete_test_runs()
    return BulkDeleteTestRunsResponse(**result)


@router.delete(
    "/{run_id}",
    response_model=RunDeleteResponse,
    responses={
        404: {"description": "Run not found"},
        409: {"description": "Cannot delete a RUNNING run"},
        500: {"description": "Internal server error"},
    },
)
def delete_run(run_id: str) -> RunDeleteResponse:
    from db import ops as _db_ops
    from db.connection import get_connection

    conn = get_connection()
    try:
        row = conn.execute("SELECT status FROM runs WHERE run_id = %s", (run_id,)).fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    if row["status"] == "RUNNING":
        raise HTTPException(status_code=409, detail="Cannot delete a RUNNING run. Cancel it first.")

    deleted = _db_ops.delete_run(run_id)

    import shutil
    from pathlib import Path
    run_dir = Path(__file__).resolve().parent.parent.parent / "work" / "runs" / run_id
    if deleted and run_dir.exists():
        try:
            shutil.rmtree(run_dir)
        except Exception as exc:
            logger.warning("[runs] Could not remove work dir %s: %s", run_dir, exc)

    return RunDeleteResponse(run_id=run_id, deleted=deleted)


@router.get(
    "/{run_id}/artifacts",
    response_model=RunArtifactListResponse,
    responses={
        404: {"description": "Run not found"},
        500: {"description": "Internal server error"},
    },
)
def get_run_artifacts(run_id: str) -> RunArtifactListResponse:
    from db.connection import get_connection

    conn = get_connection()
    try:
        run = conn.execute("SELECT run_id FROM runs WHERE run_id = %s", (run_id,)).fetchone()
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        rows = conn.execute(
            "SELECT * FROM run_artifacts WHERE run_id = %s ORDER BY created_at",
            (run_id,),
        ).fetchall()
        artifacts = [
            RunArtifactResponse(
                artifact_type=r["artifact_type"],
                file_path=r["file_path"],
                sha256=r["sha256"] or None,
                size_bytes=r["size_bytes"] or None,
                created_at=_api_time(r["created_at"]),
            )
            for r in rows
        ]
    finally:
        conn.close()

    return RunArtifactListResponse(run_id=run_id, artifacts=artifacts)


@router.get(
    "/{run_id}/artifacts/{artifact_key}/download",
    responses={404: {"description": "Run or artifact not found"}},
)
def download_run_artifact(run_id: str, artifact_key: str) -> Response:
    from db.connection import get_connection
    from urllib.parse import quote

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT run_id, topic, contents, final_mp4_path FROM runs WHERE run_id = %s", (run_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    run_dir = _run_dir(run_id)
    if not run_dir or not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="Run artifact directory not found")

    topic = _download_name(row["topic"] or "video", "video")

    def file_response(path: Path, filename: str, media_type: str) -> FileResponse:
        if not path.is_file() or not path.resolve().is_relative_to(run_dir):
            raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_key}")
        encoded = quote(filename, safe="")
        return FileResponse(
            str(path), media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
        )

    if artifact_key == "script":
        script_path = next((p for p in (run_dir / "scripts" / "script.md", run_dir / "script.md") if p.is_file()), None)
        if script_path:
            return file_response(script_path, f"{topic}-source.md", "text/markdown; charset=utf-8")
        contents = row["contents"]
        if not contents:
            raise HTTPException(status_code=404, detail="Source content not found")
        encoded = quote(f"{topic}-source.md", safe="")
        return Response(
            content=contents, media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
        )
    if artifact_key == "scenes":
        return file_response(run_dir / "scenes.json", f"{topic}-scenes.json", "application/json")
    if artifact_key == "video":
        video_path = Path(row["final_mp4_path"]) if row["final_mp4_path"] else run_dir / "video.mp4"
        return file_response(video_path, f"{topic}.mp4", "video/mp4")
    if artifact_key == "audio":
        audio_files = sorted(p for p in (run_dir / "audio").glob("scene*.mp3") if p.stat().st_size > 0)
        if not audio_files:
            raise HTTPException(status_code=404, detail="Audio artifacts not found")
        tmp = tempfile.NamedTemporaryFile(prefix="aivideo-audio-", suffix=".zip", delete=False)
        tmp.close()
        try:
            with zipfile.ZipFile(tmp.name, "w", compression=zipfile.ZIP_STORED) as archive:
                for path in audio_files:
                    archive.write(path, arcname=f"audio/{path.name}")
        except Exception:
            Path(tmp.name).unlink(missing_ok=True)
            raise
        encoded = quote(f"{topic}-voiceover-{len(audio_files)}-files.zip", safe="")
        return FileResponse(
            tmp.name, media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
            background=BackgroundTask(os.unlink, tmp.name),
        )
    raise HTTPException(status_code=404, detail=f"Unknown artifact: {artifact_key}")


@router.get(
    "/{run_id}/logs",
    response_model=RunLogsResponse,
    responses={
        404: {"description": "Run not found"},
        500: {"description": "Internal server error"},
    },
)
def get_run_logs(run_id: str, limit: int = 50) -> RunLogsResponse:
    from db.connection import get_connection

    conn = get_connection()
    try:
        run = conn.execute("SELECT run_id FROM runs WHERE run_id = %s", (run_id,)).fetchone()
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        rows = conn.execute(
            "SELECT * FROM run_stages WHERE run_id = %s ORDER BY started_at DESC LIMIT %s",
            (run_id, limit),
        ).fetchall()
    finally:
        conn.close()

    entries = [
        RunLogEntry(
            timestamp=_api_time(r["completed_at"] or r["started_at"]),
            stage_key=r["stage_key"],
            status=r["status"],
            detail=r["error_msg"] or None,
        )
        for r in reversed(rows)
    ]
    return RunLogsResponse(run_id=run_id, entries=entries)


@router.get(
    "/{run_id}/download",
    responses={
        404: {"description": "Run or file not found"},
        500: {"description": "Internal server error"},
    },
)
def download_run_file(run_id: str) -> FileResponse:
    import re
    from db.connection import get_connection
    from pathlib import Path
    from urllib.parse import quote

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status, final_mp4_path, topic FROM runs WHERE run_id = %s", (run_id,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    final_path = row["final_mp4_path"]
    if not final_path:
        raise HTTPException(status_code=404, detail="No output file recorded for this run")

    p = Path(final_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Output file not found on disk: {final_path}")

    topic = (row["topic"] or "video").strip()
    safe_topic = re.sub(r'[/\\:*?"<>|]', '_', topic).strip('_') or "video"
    encoded_filename = quote(f"{safe_topic}.mp4", safe='')
    content_disposition = f"attachment; filename*=UTF-8''{encoded_filename}"

    _MEDIA = {".mp4": "video/mp4", ".mp3": "audio/mpeg", ".md": "text/plain", ".txt": "text/plain"}
    media_type = _MEDIA.get(p.suffix.lower(), "application/octet-stream")
    return FileResponse(
        str(p),
        media_type=media_type,
        headers={"Content-Disposition": content_disposition},
    )
