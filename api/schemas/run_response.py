from __future__ import annotations

from pydantic import BaseModel


class RunStageResponse(BaseModel):
    stage_key: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_sec: float | None = None
    error_msg: str | None = None


class RunStageProgressResponse(BaseModel):
    stage_key: str
    label: str
    completed: int
    total: int
    percent: int
    updated_at: str | None = None


class RunAvailableArtifactResponse(BaseModel):
    key: str
    name: str
    filename: str
    size_bytes: int
    file_count: int = 1
    download_url: str


class RunResponse(BaseModel):
    run_id: str
    topic: str
    profile_name: str | None = None
    language: str | None = None
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    selected_input_path: str | None = None
    work_dir: str | None = None
    final_mp4_path: str | None = None
    stages: list[RunStageResponse] = []
    # enhanced fields (TASK-04)
    scene_count: int | None = None
    duration_sec: float | None = None
    artifact_count: int | None = None
    current_stage: str | None = None
    progress_percent: float | None = None
    stage_progress: RunStageProgressResponse | None = None
    available_artifacts: list[RunAvailableArtifactResponse] = []
    # generate-again prefill fields (TASK-02)
    contents: str | None = None
    target_duration_sec: int | None = None
    mode: str | None = None
    prompt_filename: str | None = None
    video_template: str | None = None
    video_templates_used: str | None = None
    run_type: str | None = None
    tts_provider: str | None = None
    tts_voice: str | None = None
    tts_fallback_used: bool | None = None
    tts_audio_duration_sec: float | None = None
    tts_cache_used: bool | None = None
    queue_position: int | None = None


class RunListResponse(BaseModel):
    runs: list[RunResponse]
    total: int


class RunArtifactResponse(BaseModel):
    artifact_type: str
    file_path: str
    sha256: str | None = None
    size_bytes: int | None = None
    created_at: str | None = None


class RunArtifactListResponse(BaseModel):
    run_id: str
    artifacts: list[RunArtifactResponse]


class RunCancelResponse(BaseModel):
    run_id: str
    status: str
    cancelled: bool


class RunDeleteResponse(BaseModel):
    run_id: str
    deleted: bool


class RunLogEntry(BaseModel):
    timestamp: str | None = None
    stage_key: str
    status: str
    detail: str | None = None


class RunLogsResponse(BaseModel):
    run_id: str
    entries: list[RunLogEntry]


class BulkDeleteTestRunsResponse(BaseModel):
    deleted_count: int
    skipped_running: int
    file_errors: int
