-- ============================================================
-- AI-Video DB Schema (PostgreSQL-only)
-- Runtime single source of truth: n100 PostgreSQL aivideo
-- ============================================================

CREATE TABLE IF NOT EXISTS prompt_templates (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT    NOT NULL UNIQUE,
    version         TEXT    NOT NULL,
    role            TEXT,
    language        TEXT    DEFAULT 'ko',
    content         TEXT    NOT NULL,
    variables       TEXT,
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS visual_templates (
    id              BIGSERIAL PRIMARY KEY,
    template_type   TEXT    NOT NULL UNIQUE,
    composition_id  TEXT    NOT NULL,
    required_keys   TEXT    NOT NULL,
    optional_keys   TEXT,
    example_data    TEXT,
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now()
);

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
    writer_high_enabled         BOOLEAN DEFAULT false,
    multi_judge_enabled         BOOLEAN DEFAULT false,
    fast_path                   BOOLEAN DEFAULT false,
    is_active                   BOOLEAN DEFAULT true,
    created_at                  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS content_adapter_strategies (
    id              BIGSERIAL PRIMARY KEY,
    strategy_id     TEXT    NOT NULL UNIQUE,
    content_type    TEXT    NOT NULL,
    scene_count     INTEGER NOT NULL,
    scene_plans     TEXT    NOT NULL,
    description     TEXT,
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runs (
    id                      BIGSERIAL PRIMARY KEY,
    run_id                  TEXT    NOT NULL UNIQUE,
    topic                   TEXT    NOT NULL,
    profile_name            TEXT,
    started_at              TIMESTAMPTZ NOT NULL,
    completed_at            TIMESTAMPTZ,
    status                  TEXT    DEFAULT 'RUNNING',
    selected_input_path     TEXT,
    source_files            TEXT,
    generated_files         TEXT,
    work_dir                TEXT,
    final_mp4_path          TEXT,
    created_at              TIMESTAMPTZ DEFAULT now(),
    language                TEXT    DEFAULT 'ko',
    contents                TEXT,
    target_duration_sec     INTEGER DEFAULT 120,
    mode                    TEXT    DEFAULT 'template',
    prompt_filename         TEXT,
    video_template          TEXT,
    video_templates_used    TEXT,
    run_type                TEXT    DEFAULT 'TEST',
    tts_provider            TEXT    DEFAULT 'azure',
    tts_fallback_used       BOOLEAN DEFAULT false,
    tts_voice               TEXT,
    tts_audio_duration_sec  REAL,
    tts_cache_used          BOOLEAN DEFAULT false,
    error_message           TEXT,
    queue_order             INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS run_stages (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT    NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    stage_key       TEXT    NOT NULL,
    status          TEXT    NOT NULL,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    duration_sec    REAL,
    error_msg       TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (run_id, stage_key)
);

CREATE TABLE IF NOT EXISTS run_artifacts (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT    NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    artifact_type   TEXT    NOT NULL,
    file_path       TEXT    NOT NULL,
    sha256          TEXT,
    size_bytes      INTEGER,
    created_at      TIMESTAMPTZ DEFAULT now()
);

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
    template_data   TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (run_id, scene_index)
);

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
    quality_score       REAL,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS qa_results (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT    NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    check_name      TEXT    NOT NULL,
    passed          BOOLEAN NOT NULL,
    detail          TEXT,
    checked_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (run_id, check_name)
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              TEXT REFERENCES runs(run_id) ON DELETE CASCADE,
    task_id             TEXT,
    role                TEXT    NOT NULL,
    provider            TEXT    NOT NULL,
    model               TEXT,
    status              TEXT    NOT NULL,
    input_chars         INTEGER,
    output_chars        INTEGER,
    estimated_cost_krw  REAL,
    duration_sec        REAL,
    error_msg           TEXT,
    is_api_provider     BOOLEAN DEFAULT false,
    called_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE runs ADD COLUMN IF NOT EXISTS language TEXT DEFAULT 'ko';
ALTER TABLE runs ADD COLUMN IF NOT EXISTS contents TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS target_duration_sec INTEGER DEFAULT 120;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS mode TEXT DEFAULT 'template';
ALTER TABLE runs ADD COLUMN IF NOT EXISTS prompt_filename TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS video_template TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS video_templates_used TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS run_type TEXT DEFAULT 'TEST';
ALTER TABLE runs ADD COLUMN IF NOT EXISTS tts_provider TEXT DEFAULT 'azure';
ALTER TABLE runs ADD COLUMN IF NOT EXISTS tts_fallback_used BOOLEAN DEFAULT false;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS tts_voice TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS tts_audio_duration_sec REAL;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS tts_cache_used BOOLEAN DEFAULT false;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS queue_order INTEGER DEFAULT 0;
