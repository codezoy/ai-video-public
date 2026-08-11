"""Queue management endpoints."""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/queue", tags=["Queue"])


class ReorderRequest(BaseModel):
    run_ids: list[str]


class BulkCancelRequest(BaseModel):
    run_ids: list[str] | None = None  # None = cancel all QUEUED


@router.get("/status")
def get_queue_status() -> dict:
    from db import ops as _db_ops
    from pipelines.worker_state import get_worker_status

    status = _db_ops.get_queue_status()
    worker = get_worker_status()
    avg_sec = _db_ops.get_avg_runtime_sec()
    return {
        **status,
        "max_concurrent_runs": int(os.getenv("MAX_CONCURRENT_RUNS", "1")),
        "worker_running": worker["worker_running"],
        "avg_runtime_sec": avg_sec,
        "avg_runtime_minutes": round(avg_sec / 60, 1) if avg_sec else None,
    }


@router.post("/bulk-cancel")
def bulk_cancel_queue(body: BulkCancelRequest) -> dict:
    from db import ops as _db_ops

    result = _db_ops.bulk_cancel_queued(body.run_ids)
    if not result["ok"]:
        raise HTTPException(
            status_code=result.get("status_code", 400), detail=result["error"]
        )
    return result


@router.post("/reorder")
def bulk_reorder_queue(body: ReorderRequest) -> dict:
    from db import ops as _db_ops

    result = _db_ops.reorder_queue(body.run_ids)
    if not result["ok"]:
        raise HTTPException(
            status_code=result.get("status_code", 400), detail=result["error"]
        )
    return result


@router.post("/{run_id}/move-up")
def move_run_up(run_id: str) -> dict:
    from db import ops as _db_ops

    result = _db_ops.move_queue_run(run_id, "up")
    if not result["ok"]:
        raise HTTPException(
            status_code=result.get("status_code", 400), detail=result["error"]
        )
    return result


@router.post("/{run_id}/move-down")
def move_run_down(run_id: str) -> dict:
    from db import ops as _db_ops

    result = _db_ops.move_queue_run(run_id, "down")
    if not result["ok"]:
        raise HTTPException(
            status_code=result.get("status_code", 400), detail=result["error"]
        )
    return result


@router.post("/{run_id}/move-top")
def move_run_top(run_id: str) -> dict:
    from db import ops as _db_ops

    result = _db_ops.move_queue_run(run_id, "top")
    if not result["ok"]:
        raise HTTPException(
            status_code=result.get("status_code", 400), detail=result["error"]
        )
    return result


@router.post("/{run_id}/move-bottom")
def move_run_bottom(run_id: str) -> dict:
    from db import ops as _db_ops

    result = _db_ops.move_queue_run(run_id, "bottom")
    if not result["ok"]:
        raise HTTPException(
            status_code=result.get("status_code", 400), detail=result["error"]
        )
    return result
