"""Worker status endpoint."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/worker", tags=["Worker"])


@router.get("/status")
def get_worker_status() -> dict:
    from db import ops as _db_ops
    from pipelines.worker_state import get_worker_status

    status = get_worker_status()
    queue = _db_ops.get_queue_status()
    return {
        **status,
        "queued_count": queue.get("queued_count", 0),
        "running_count": queue.get("running_count", 0),
    }
