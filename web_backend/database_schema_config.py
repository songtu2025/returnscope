from __future__ import annotations

CONFIG_SCHEMA = """CREATE TABLE IF NOT EXISTS api_connections (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL,
    active_version_id TEXT,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_models (
    id TEXT PRIMARY KEY,
    connection_id TEXT NOT NULL REFERENCES api_connections(id) ON DELETE CASCADE,
    model_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    supported_efforts_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    validation_status TEXT NOT NULL DEFAULT 'draft',
    validation_message TEXT NOT NULL DEFAULT '',
    validated_at TEXT,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_by TEXT NOT NULL REFERENCES users(id),
    updated_at TEXT NOT NULL,
    UNIQUE(connection_id, model_key)
);
CREATE INDEX IF NOT EXISTS idx_api_models_connection
ON api_models(connection_id, active, updated_at DESC);

CREATE TABLE IF NOT EXISTS api_validation_runs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('model', 'config')),
    target_id TEXT NOT NULL,
    connection_id TEXT NOT NULL REFERENCES api_connections(id) ON DELETE CASCADE,
    config_version_id TEXT NOT NULL REFERENCES api_config_versions(id),
    status TEXT NOT NULL DEFAULT 'queued',
    stage TEXT NOT NULL DEFAULT 'queued',
    endpoint TEXT NOT NULL,
    timeout_seconds INTEGER NOT NULL,
    items_json TEXT NOT NULL,
    completed_count INTEGER NOT NULL DEFAULT 0,
    total_count INTEGER NOT NULL,
    error_category TEXT,
    error_message TEXT,
    suggestion TEXT,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_api_validation_runs_connection
ON api_validation_runs(connection_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_api_validation_runs_target
ON api_validation_runs(target_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS api_validation_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES api_validation_runs(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    stage TEXT NOT NULL,
    message TEXT NOT NULL,
    model_key TEXT,
    data_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_api_validation_events_run
ON api_validation_events(run_id, id);

CREATE TABLE IF NOT EXISTS api_config_versions (
    id TEXT PRIMARY KEY,
    connection_id TEXT NOT NULL REFERENCES api_connections(id),
    version INTEGER NOT NULL,
    base_url TEXT NOT NULL,
    api_key_ciphertext TEXT NOT NULL,
    primary_model TEXT NOT NULL,
    primary_effort TEXT NOT NULL,
    cheap_model TEXT,
    cheap_effort TEXT,
    secondary_model TEXT,
    secondary_effort TEXT,
    cheap_audit_percent INTEGER NOT NULL DEFAULT 5,
    requests_per_minute INTEGER NOT NULL DEFAULT 60,
    max_workers INTEGER NOT NULL DEFAULT 4,
    timeout_seconds INTEGER NOT NULL DEFAULT 120,
    change_note TEXT NOT NULL DEFAULT '',
    validation_status TEXT NOT NULL DEFAULT 'draft',
    validation_message TEXT NOT NULL DEFAULT '',
    validated_at TEXT,
    published_at TEXT,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    UNIQUE(connection_id, version)
);
CREATE INDEX IF NOT EXISTS idx_api_versions_connection
ON api_config_versions(connection_id, version DESC);

"""
