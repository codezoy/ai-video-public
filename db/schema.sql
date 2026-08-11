-- ============================================================
-- AI-Video DB Schema (PostgreSQL)
-- Runtime DB: PostgreSQL only
-- Destructive migrations are intentionally not used here.
-- ============================================================

-- ============================================================
-- T1: prompt_templates
-- ============================================================
CREATE TABLE IF NOT EXISTS prompt_templates (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT    NOT NULL UNIQUE,
    version         TEXT    NOT NULL,
    role            TEXT,
    language        TEXT    DEFAULT 'ko',
    content         TEXT    NOT NULL,
    variables       JSONB,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- T2: visual_templates
-- ============================================================
CREATE TABLE IF NOT EXISTS visual_templates (
    id              BIGSERIAL PRIMARY KEY,
    template_type   TEXT    NOT NULL UNIQUE,
    composition_id  TEXT    NOT NULL,
    required_keys   JSONB   NOT NULL,
    optional_keys   JSONB,
    example_data    JSONB,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- T3: generation_profiles
-- ============================================================
CREATE TABLE IF NOT EXISTS generation_profiles (
    id                          BIGSERIAL PRIMARY KEY,
    name                        TEXT    NOT NULL UNIQUE,
    max_duration_sec            INTEGER NOT NULL,
    min_scenes                  INTEGER NOT NULL,
    max_scenes                  INTEGER NOT NULL,
    max_scene_narration_chars   INTEGER NOT NULL,
    max_total_narration_chars   INTEGER NOT NULL,
    critique_max_runs           INTEGER DEFAULT 2,
    regen_max_runs              INTEGER DEFAULT 2,
    writer_high_enabled         BOOLEAN DEFAULT FALSE,
    multi_judge_enabled         BOOLEAN DEFAULT FALSE,
    fast_path                   BOOLEAN DEFAULT FALSE,
    is_active                   BOOLEAN DEFAULT TRUE,
    created_at                  TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- T4: content_adapter_strategies
-- ============================================================
CREATE TABLE IF NOT EXISTS content_adapter_strategies (
    id              BIGSERIAL PRIMARY KEY,
    strategy_id     TEXT    NOT NULL UNIQUE,
    content_type    TEXT    NOT NULL,
    scene_count     INTEGER NOT NULL,
    scene_plans     JSONB   NOT NULL,
    description     TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- T5: runs [P0]
-- ============================================================
CREATE TABLE IF NOT EXISTS runs (
    id                      BIGSERIAL PRIMARY KEY,
    run_id                  TEXT    NOT NULL UNIQUE,
    topic                   TEXT    NOT NULL,
    profile_name            TEXT,
    language                TEXT    DEFAULT 'ko',
    started_at              TIMESTAMPTZ NOT NULL,
    completed_at            TIMESTAMPTZ,
    status                  TEXT    DEFAULT 'RUNNING',
    selected_input_path     TEXT,
    source_files            JSONB,
    generated_files         JSONB,
    work_dir                TEXT,
    final_mp4_path          TEXT,
    contents                TEXT,
    target_duration_sec     INTEGER DEFAULT 120,
    mode                    TEXT    DEFAULT 'template',
    prompt_filename         TEXT,
    video_template          TEXT,
    video_templates_used    TEXT,
    run_type                TEXT    DEFAULT 'TEST',
    tts_provider            TEXT    DEFAULT 'azure',
    tts_fallback_used       BOOLEAN DEFAULT FALSE,
    tts_voice               TEXT,
    tts_audio_duration_sec  DOUBLE PRECISION,
    tts_cache_used          BOOLEAN DEFAULT FALSE,
    error_message           TEXT,
    queue_order             INTEGER DEFAULT 0,
    created_at              TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- T6: run_stages [P0]
-- ============================================================
CREATE TABLE IF NOT EXISTS run_stages (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT    NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    stage_key       TEXT    NOT NULL,
    status          TEXT    NOT NULL,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    duration_sec    DOUBLE PRECISION,
    error_msg       TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (run_id, stage_key)
);

-- ============================================================
-- T7: run_artifacts [P0]
-- ============================================================
CREATE TABLE IF NOT EXISTS run_artifacts (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT    NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    artifact_type   TEXT    NOT NULL,
    file_path       TEXT    NOT NULL,
    sha256          TEXT,
    size_bytes      BIGINT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- T8: run_scene_plans [P1]
-- ============================================================
CREATE TABLE IF NOT EXISTS run_scene_plans (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT    NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    scene_index     INTEGER NOT NULL,
    scene_id        TEXT,
    title           TEXT,
    purpose         TEXT,
    visual_type     TEXT,
    narration_text  TEXT,
    narration_chars INTEGER,
    template_data   JSONB,
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (run_id, scene_index)
);

-- ============================================================
-- T9: run_scripts [P1]
-- ============================================================
CREATE TABLE IF NOT EXISTS run_scripts (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              TEXT    NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    prompt_template_id  BIGINT REFERENCES prompt_templates(id),
    script_type         TEXT    NOT NULL,
    content             TEXT,
    content_path        TEXT,
    char_count          INTEGER,
    token_estimate      INTEGER,
    language            TEXT    DEFAULT 'ko',
    version             INTEGER DEFAULT 1,
    quality_score       DOUBLE PRECISION,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- T10: qa_results [P0]
-- ============================================================
CREATE TABLE IF NOT EXISTS qa_results (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT    NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    check_name      TEXT    NOT NULL,
    passed          BOOLEAN NOT NULL,
    detail          TEXT,
    checked_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (run_id, check_name)
);

-- ============================================================
-- T11: llm_calls [P0]
-- ============================================================
CREATE TABLE IF NOT EXISTS llm_calls (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              TEXT,
    task_id             TEXT,
    role                TEXT    NOT NULL,
    provider            TEXT    NOT NULL,
    model               TEXT,
    status              TEXT    NOT NULL,
    input_chars         INTEGER,
    output_chars        INTEGER,
    estimated_cost_krw  DOUBLE PRECISION,
    duration_sec        DOUBLE PRECISION,
    error_msg           TEXT,
    is_api_provider     BOOLEAN DEFAULT FALSE,
    called_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Additive migrations for databases initialized by older ai-video versions.
ALTER TABLE runs ADD COLUMN IF NOT EXISTS language TEXT DEFAULT 'ko';
ALTER TABLE runs ADD COLUMN IF NOT EXISTS contents TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS target_duration_sec INTEGER DEFAULT 120;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS mode TEXT DEFAULT 'template';
ALTER TABLE runs ADD COLUMN IF NOT EXISTS prompt_filename TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS video_template TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS video_templates_used TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS run_type TEXT DEFAULT 'TEST';
ALTER TABLE runs ADD COLUMN IF NOT EXISTS tts_provider TEXT DEFAULT 'azure';
ALTER TABLE runs ADD COLUMN IF NOT EXISTS tts_fallback_used BOOLEAN DEFAULT FALSE;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS tts_voice TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS tts_audio_duration_sec DOUBLE PRECISION;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS tts_cache_used BOOLEAN DEFAULT FALSE;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS queue_order INTEGER DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_runs_status_queue ON runs (status, queue_order, created_at);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_run_stages_run_id ON run_stages (run_id);
CREATE INDEX IF NOT EXISTS idx_run_artifacts_run_id ON run_artifacts (run_id);
