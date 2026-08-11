"""Non-blocking PostgreSQL P0 operations for pipeline DB recording.

All public functions silently catch exceptions so that DB failures
never interrupt video generation.
"""
from __future__ import annotations

import datetime
import hashlib
import logging
from pathlib import Path

from psycopg2.extras import Json

logger = logging.getLogger(__name__)

STALE_RUN_TIMEOUT_HOURS = 24

_initialized = False


def _utc_now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def _conn():
    from db.connection import get_connection
    return get_connection()


def init(db_path: Path | None = None) -> None:
    global _initialized
    if _initialized:
        return
    try:
        from db.connection import init_db
        if db_path is not None:
            raise RuntimeError("db_path is not supported; configure PostgreSQL with AIVIDEO_DATABASE_URL or DATABASE_URL")
        init_db()
        _initialized = True
    except Exception as exc:
        logger.error("[DB] init 실패: %s", exc)
        raise


def create_run(
    run_id: str,
    topic: str,
    input_path: str,
    work_dir: str,
    profile_name: str = "",
    language: str = "ko",
    contents: str | None = None,
    target_duration_sec: int = 120,
    mode: str = "template",
    prompt_filename: str | None = None,
    run_type: str = "TEST",
    tts_provider: str = "azure",
    tts_voice: str | None = None,
) -> None:
    try:
        conn = _conn()
        try:
            now = _utc_now()
            conn.execute(
                """
                INSERT INTO runs
                    (run_id, topic, profile_name, language, created_at, started_at,
                     status, selected_input_path, source_files, work_dir,
                     contents, target_duration_sec, mode, prompt_filename, run_type,
                     tts_provider, tts_voice, queue_order)
                VALUES (%s, %s, %s, %s, %s, %s, 'QUEUED', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        (SELECT COALESCE(MAX(queue_order), 0) + 1 FROM runs))
                ON CONFLICT (run_id) DO NOTHING
                """,
                (
                    run_id, topic, profile_name, language, now, now,
                    input_path, Json([input_path]), work_dir,
                    contents, target_duration_sec, mode, prompt_filename, run_type,
                    tts_provider, tts_voice,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[DB] create_run 실패 (무시): %s", exc)


def update_tts_metadata(
    run_id: str,
    tts_voice: str | None = None,
    tts_audio_duration_sec: float | None = None,
    tts_cache_used: bool = False,
) -> None:
    try:
        conn = _conn()
        try:
            conn.execute(
                """
                UPDATE runs
                SET tts_voice=%s, tts_audio_duration_sec=%s, tts_cache_used=%s
                WHERE run_id=%s
                """,
                (tts_voice, tts_audio_duration_sec, tts_cache_used, run_id),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[DB] update_tts_metadata 실패 (무시): %s", exc)


def record_stage(
    run_id: str,
    stage_key: str,
    status: str,
    duration_sec: float,
    error_msg: str = "",
) -> None:
    try:
        now = _utc_now()
        conn = _conn()
        try:
            conn.execute(
                """
                INSERT INTO run_stages
                    (run_id, stage_key, status, started_at, completed_at, duration_sec, error_msg)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(run_id, stage_key) DO UPDATE SET
                    status=excluded.status,
                    completed_at=excluded.completed_at,
                    duration_sec=excluded.duration_sec,
                    error_msg=excluded.error_msg
                """,
                (run_id, stage_key, status, now, now, duration_sec, error_msg),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[DB] record_stage 실패 (무시): %s", exc)


def record_artifact(run_id: str, artifact_type: str, file_path: str) -> None:
    try:
        p = Path(file_path)
        sha256, size_bytes = "", 0
        if p.exists():
            raw = p.read_bytes()
            sha256 = hashlib.sha256(raw).hexdigest()
            size_bytes = len(raw)
        conn = _conn()
        try:
            conn.execute(
                """
                INSERT INTO run_artifacts
                    (run_id, artifact_type, file_path, sha256, size_bytes)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (run_id, artifact_type, file_path, sha256, size_bytes),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[DB] record_artifact 실패 (무시): %s", exc)


def cancel_run(run_id: str) -> bool:
    """Set run status to CANCELLED if currently RUNNING or QUEUED. Returns True if updated."""
    try:
        conn = _conn()
        try:
            cur = conn.execute(
                "UPDATE runs SET status='CANCELLED', completed_at=%s WHERE run_id=%s AND status IN ('RUNNING', 'QUEUED')",
                (_utc_now(), run_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[DB] cancel_run 실패 (무시): %s", exc)
        return False


def delete_run(run_id: str) -> bool:
    """Delete a non-RUNNING run and its stages/artifacts. Returns True if deleted."""
    try:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT status FROM runs WHERE run_id = %s", (run_id,)
            ).fetchone()
            if row is None:
                return False
            if row["status"] == "RUNNING":
                logger.warning("[DB] delete_run rejected: run %s is still RUNNING", run_id)
                return False
            conn.execute("DELETE FROM run_stages WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM run_artifacts WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM run_scene_plans WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[DB] delete_run 실패 (무시): %s", exc)
        return False


def mark_stale_runs_failed(stale_hours: int = STALE_RUN_TIMEOUT_HOURS, exclude_run_ids: set[str] | None = None) -> int:
    """Mark orphaned RUNNING runs as FAILED. Skips run_ids in exclude_run_ids (active threads)."""
    error_msg = f"Marked failed by stale run cleanup ({stale_hours}h timeout)"
    try:
        conn = _conn()
        try:
            if exclude_run_ids:
                placeholders = ",".join(["%s"] * len(exclude_run_ids))
                params: tuple = (_utc_now(), error_msg, *exclude_run_ids, stale_hours)
                cur = conn.execute(
                    f"""
                    UPDATE runs SET status='FAILED', completed_at=%s, error_message=%s
                    WHERE status='RUNNING'
                    AND run_id NOT IN ({placeholders})
                    AND started_at < (now() - (%s * interval '1 hour'))
                    """,
                    params,
                )
            else:
                cur = conn.execute(
                    """
                    UPDATE runs SET status='FAILED', completed_at=%s, error_message=%s
                    WHERE status='RUNNING'
                    AND started_at < (now() - (%s * interval '1 hour'))
                    """,
                    (_utc_now(), error_msg, stale_hours),
                )
            conn.commit()
            count = cur.rowcount
            if count > 0:
                logger.warning("[DB] Marked %d stale RUNNING run(s) as FAILED", count)
            return count
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[DB] mark_stale_runs_failed 실패 (무시): %s", exc)
        return 0


def update_video_template(
    run_id: str,
    video_template: str,
    video_templates_used: str,
) -> None:
    try:
        conn = _conn()
        try:
            conn.execute(
                "UPDATE runs SET video_template=%s, video_templates_used=%s WHERE run_id=%s",
                (video_template, video_templates_used, run_id),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[DB] update_video_template 실패 (무시): %s", exc)


def bulk_delete_test_runs() -> dict:
    """Delete all TEST runs (excluding RUNNING and PRODUCTION). Returns stats."""
    import shutil
    from pathlib import Path

    proj_root = Path(__file__).resolve().parent.parent
    deleted_count = 0
    skipped_running = 0
    file_errors = 0

    try:
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT run_id, status FROM runs WHERE run_type = 'TEST' OR run_type IS NULL"
            ).fetchall()
            run_ids = []
            for row in rows:
                if row["status"] == "RUNNING":
                    skipped_running += 1
                    continue
                run_ids.append(row["run_id"])

            for run_id in run_ids:
                conn.execute("DELETE FROM run_stages WHERE run_id = %s", (run_id,))
                conn.execute("DELETE FROM run_artifacts WHERE run_id = %s", (run_id,))
                conn.execute("DELETE FROM run_scene_plans WHERE run_id = %s", (run_id,))
                conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
                run_dir = proj_root / "work" / "runs" / run_id
                if run_dir.exists():
                    try:
                        shutil.rmtree(run_dir)
                    except Exception as e:
                        logger.warning("[DB] Could not remove work dir %s: %s", run_dir, e)
                        file_errors += 1
                deleted_count += 1

            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[DB] bulk_delete_test_runs 실패: %s", exc)

    return {
        "deleted_count": deleted_count,
        "skipped_running": skipped_running,
        "file_errors": file_errors,
    }


def resume_run(run_id: str) -> dict | None:
    """Reset a FAILED/CANCELLED run back to QUEUED for re-execution by the worker.
    Returns the run row dict (pre-reset values), or None if not found or not resumable."""
    _RESUMABLE_STATUSES = {"FAILED", "CANCELLED"}
    try:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT * FROM runs WHERE run_id = %s", (run_id,)
            ).fetchone()
            if row is None:
                return None
            if row["status"] not in _RESUMABLE_STATUSES:
                return None
            conn.execute(
                "UPDATE runs SET status='QUEUED', completed_at=NULL WHERE run_id=%s",
                (run_id,),
            )
            conn.commit()
            return dict(row)
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[DB] resume_run 실패 (무시): %s", exc)
        return None


_MAX_CLAIM_RETRIES = 5


def claim_queued_run(max_concurrent: int) -> dict | None:
    """Atomically claim the next QUEUED run for execution.

    Uses optimistic locking: SELECT candidate → atomic UPDATE with capacity
    subquery guard.  Returns the claimed run row, or None if queue is empty or
    at capacity.  Retries up to _MAX_CLAIM_RETRIES times on concurrent races.
    """
    try:
        conn = _conn()
        try:
            for _ in range(_MAX_CLAIM_RETRIES):
                running_count = conn.execute(
                    "SELECT COUNT(*) FROM runs WHERE status='RUNNING'"
                ).fetchone()[0]
                if running_count >= max_concurrent:
                    return None
                candidate = conn.execute(
                    "SELECT * FROM runs WHERE status='QUEUED' ORDER BY queue_order ASC, created_at ASC LIMIT 1"
                ).fetchone()
                if candidate is None:
                    return None
                now = _utc_now()
                # Capacity check is embedded in the WHERE clause so the UPDATE
                # is fully atomic — prevents exceeding max_concurrent even when
                # multiple workers race.
                cur = conn.execute(
                    """UPDATE runs SET status='RUNNING', started_at=%s
                       WHERE run_id=%s AND status='QUEUED'
                       AND (SELECT COUNT(*) FROM runs WHERE status='RUNNING') < %s""",
                    (now, candidate["run_id"], max_concurrent),
                )
                conn.commit()
                if cur.rowcount > 0:
                    row = conn.execute(
                        "SELECT * FROM runs WHERE run_id=%s", (candidate["run_id"],)
                    ).fetchone()
                    return dict(row) if row else None
            return None
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[DB] claim_queued_run 실패 (무시): %s", exc)
        return None


def get_queue_status() -> dict:
    """Return counts of QUEUED and RUNNING runs, and the oldest queued timestamp."""
    try:
        conn = _conn()
        try:
            queued_count = conn.execute(
                "SELECT COUNT(*) FROM runs WHERE status='QUEUED'"
            ).fetchone()[0]
            running_count = conn.execute(
                "SELECT COUNT(*) FROM runs WHERE status='RUNNING'"
            ).fetchone()[0]
            oldest = conn.execute(
                "SELECT created_at FROM runs WHERE status='QUEUED' ORDER BY queue_order ASC LIMIT 1"
            ).fetchone()
            oldest_queued_at = oldest["created_at"] if oldest else None
            return {
                "queued_count": queued_count,
                "running_count": running_count,
                "oldest_queued_at": oldest_queued_at,
            }
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[DB] get_queue_status 실패 (무시): %s", exc)
        return {"queued_count": 0, "running_count": 0, "oldest_queued_at": None}


def get_queue_position(run_id: str) -> int | None:
    """Return 1-based queue position for a QUEUED run, or None if not QUEUED."""
    try:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT queue_order, status FROM runs WHERE run_id=%s", (run_id,)
            ).fetchone()
            if row is None or row["status"] != "QUEUED":
                return None
            pos = conn.execute(
                "SELECT COUNT(*) FROM runs WHERE status='QUEUED' AND queue_order <= %s",
                (row["queue_order"],),
            ).fetchone()[0]
            # Re-check status in case it changed between the two queries.
            recheck = conn.execute(
                "SELECT status FROM runs WHERE run_id=%s", (run_id,)
            ).fetchone()
            if recheck is None or recheck["status"] != "QUEUED":
                return None
            return pos
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[DB] get_queue_position 실패 (무시): %s", exc)
        return None


def _normalize_queue_orders(conn, ordered_run_ids: list[str]) -> None:
    for idx, run_id in enumerate(ordered_run_ids, start=1):
        conn.execute("UPDATE runs SET queue_order=%s WHERE run_id=%s", (idx, run_id))


def move_queue_run(run_id: str, direction: str) -> dict:
    """Move a QUEUED run up/down/top/bottom. Returns {ok, new_position} or {ok, error, status_code}."""
    try:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT run_id, status FROM runs WHERE run_id=%s", (run_id,)
            ).fetchone()
            if row is None:
                return {"ok": False, "error": "Run not found", "status_code": 404}
            if row["status"] != "QUEUED":
                return {
                    "ok": False,
                    "error": f"Run is not QUEUED (status={row['status']})",
                    "status_code": 409,
                }
            queued = conn.execute(
                "SELECT run_id FROM runs WHERE status='QUEUED' ORDER BY queue_order ASC"
            ).fetchall()
            ids = [r["run_id"] for r in queued]
            if run_id not in ids:
                return {"ok": False, "error": "Run not in queue", "status_code": 404}
            if direction not in ("up", "down", "top", "bottom"):
                return {"ok": False, "error": f"Invalid direction: {direction}", "status_code": 400}
            idx = ids.index(run_id)
            if direction == "up" and idx > 0:
                ids[idx], ids[idx - 1] = ids[idx - 1], ids[idx]
            elif direction == "down" and idx < len(ids) - 1:
                ids[idx], ids[idx + 1] = ids[idx + 1], ids[idx]
            elif direction == "top":
                ids.pop(idx)
                ids.insert(0, run_id)
            elif direction == "bottom":
                ids.pop(idx)
                ids.append(run_id)
            _normalize_queue_orders(conn, ids)
            conn.commit()
            return {"ok": True, "new_position": ids.index(run_id) + 1}
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[DB] move_queue_run 실패: %s", exc)
        return {"ok": False, "error": str(exc), "status_code": 500}


def reorder_queue(run_ids: list[str]) -> dict:
    """Reorder all QUEUED runs by providing the complete ordered run_id list."""
    try:
        conn = _conn()
        try:
            if len(set(run_ids)) != len(run_ids):
                return {"ok": False, "error": "Duplicate run_ids", "status_code": 400}
            for rid in run_ids:
                row = conn.execute(
                    "SELECT run_id, status FROM runs WHERE run_id=%s", (rid,)
                ).fetchone()
                if row is None:
                    return {"ok": False, "error": f"Run not found: {rid}", "status_code": 404}
                if row["status"] != "QUEUED":
                    return {
                        "ok": False,
                        "error": f"Run {rid} is not QUEUED (status={row['status']})",
                        "status_code": 409,
                    }
            all_queued = {
                r["run_id"]
                for r in conn.execute(
                    "SELECT run_id FROM runs WHERE status='QUEUED'"
                ).fetchall()
            }
            if all_queued != set(run_ids):
                return {
                    "ok": False,
                    "error": "run_ids must include all QUEUED runs",
                    "status_code": 400,
                }
            _normalize_queue_orders(conn, run_ids)
            conn.commit()
            return {"ok": True, "count": len(run_ids)}
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[DB] reorder_queue 실패: %s", exc)
        return {"ok": False, "error": str(exc), "status_code": 500}


def get_avg_runtime_sec(limit: int = 10) -> float | None:
    """Return average runtime (seconds) from recent DONE runs that have both timestamps."""
    try:
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT EXTRACT(EPOCH FROM (completed_at - started_at)) AS dur"
                " FROM runs WHERE status='DONE' AND started_at IS NOT NULL AND completed_at IS NOT NULL"
                " AND EXTRACT(EPOCH FROM (completed_at - started_at)) > 60"
                " ORDER BY completed_at DESC LIMIT %s",
                (limit,),
            ).fetchall()
            if not rows:
                return None
            return float(sum(r["dur"] for r in rows) / len(rows))
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[DB] get_avg_runtime_sec 실패 (무시): %s", exc)
        return None


def bulk_cancel_queued(run_ids: list[str] | None = None) -> dict:
    """Cancel QUEUED runs. run_ids=None cancels all QUEUED. Returns cancelled_count."""
    try:
        conn = _conn()
        try:
            now = _utc_now()
            if run_ids is None:
                cur = conn.execute(
                    "UPDATE runs SET status='CANCELLED', completed_at=%s WHERE status='QUEUED'",
                    (now,),
                )
                conn.commit()
                return {"ok": True, "cancelled_count": cur.rowcount}
            if not run_ids:
                return {"ok": True, "cancelled_count": 0}
            placeholders = ",".join(["%s"] * len(run_ids))
            cur = conn.execute(
                f"UPDATE runs SET status='CANCELLED', completed_at=%s"
                f" WHERE run_id IN ({placeholders}) AND status='QUEUED'",
                [now, *run_ids],
            )
            conn.commit()
            not_queued = len(run_ids) - cur.rowcount
            if not_queued > 0:
                logger.info("[DB] bulk_cancel_queued: %d skipped (RUNNING or already done)", not_queued)
            return {"ok": True, "cancelled_count": cur.rowcount}
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[DB] bulk_cancel_queued 실패: %s", exc)
        return {"ok": False, "error": str(exc), "status_code": 500}


def complete_run(
    run_id: str,
    final_mp4_path: str = "",
    generated_files: list[str] | None = None,
    status: str = "DONE",
) -> None:
    try:
        conn = _conn()
        try:
            conn.execute(
                """
                UPDATE runs
                SET status=%s, completed_at=%s, final_mp4_path=%s, generated_files=%s
                WHERE run_id=%s
                """,
                (status, _utc_now(), final_mp4_path, Json(generated_files or []), run_id),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[DB] complete_run 실패 (무시): %s", exc)
