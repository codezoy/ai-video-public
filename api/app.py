"""AI-Video FastAPI application — production default port 8902."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import health, profiles, queue, runs, templates, tts, worker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from db import ops as _db_ops
    _db_ops.init()
    logger.info("[startup] DB initialized")
    cleaned = _db_ops.mark_stale_runs_failed()
    if cleaned > 0:
        logger.info("[startup] Cleaned up %d stale RUNNING run(s)", cleaned)
    yield


app = FastAPI(
    title="AI-Video Pipeline API",
    description="REST API for AI-Video automated pipeline",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=400, content=jsonable_encoder({"detail": exc.errors()}))


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(runs.router)
app.include_router(queue.router)
app.include_router(worker.router)
app.include_router(profiles.router)
app.include_router(templates.router)
app.include_router(tts.router)
