from __future__ import annotations

TASK_SCHEMA = """CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    owner_id TEXT NOT NULL REFERENCES users(id),
    dataset_version_id TEXT NOT NULL REFERENCES dataset_versions(id),
    product_version_id TEXT NOT NULL REFERENCES dataset_versions(id),
    config_version_id TEXT NOT NULL REFERENCES api_config_versions(id),
    store TEXT NOT NULL,
    listing TEXT,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    progress_current INTEGER NOT NULL DEFAULT 0,
    progress_total INTEGER NOT NULL DEFAULT 0,
    progress_percent REAL NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    error TEXT,
    snapshot_json TEXT NOT NULL,
    metrics_json TEXT,
    result_file_path TEXT,
    results_json_path TEXT,
    result_version INTEGER NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    pause_requested INTEGER NOT NULL DEFAULT 0,
    max_parallel_segments INTEGER NOT NULL DEFAULT 3,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    heartbeat_at TEXT,
    last_scheduled_at TEXT,
    archived_at TEXT,
    archived_by TEXT REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_tasks_owner_status
ON tasks(owner_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_status_created
ON tasks(status, created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_dataset_version
ON tasks(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_tasks_product_version
ON tasks(product_version_id);

CREATE TABLE IF NOT EXISTS task_segments (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    segment_key TEXT NOT NULL,
    agent_key TEXT NOT NULL,
    agent_family TEXT NOT NULL,
    logic_version TEXT,
    taxonomy_version TEXT NOT NULL,
    model_policy_version TEXT,
    standard_version_id TEXT REFERENCES classification_standard_versions(id),
    model_policy_json TEXT,
    claims_version TEXT,
    scope_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    record_count INTEGER NOT NULL DEFAULT 0,
    unique_comments INTEGER NOT NULL DEFAULT 0,
    progress_current INTEGER NOT NULL DEFAULT 0,
    progress_total INTEGER NOT NULL DEFAULT 0,
    model_calls INTEGER NOT NULL DEFAULT 0,
    cache_hits INTEGER NOT NULL DEFAULT 0,
    model_failures INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    variants_json TEXT NOT NULL DEFAULT '[]',
    classification_keys_json TEXT NOT NULL DEFAULT '[]',
    execution_order INTEGER NOT NULL DEFAULT 0,
    requested_action TEXT,
    revision INTEGER NOT NULL DEFAULT 1,
    retry_count INTEGER NOT NULL DEFAULT 0,
    heartbeat_at TEXT,
    result_file_path TEXT,
    result_json_path TEXT,
    result_version INTEGER NOT NULL DEFAULT 0,
    result_version_id TEXT,
    result_publish_status TEXT,
    result_quality_status TEXT,
    result_published_at TEXT,
    result_publish_error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    UNIQUE(task_id, segment_key)
);
CREATE INDEX IF NOT EXISTS idx_task_segments_task
ON task_segments(task_id, segment_key);
CREATE INDEX IF NOT EXISTS idx_task_segments_status_order
ON task_segments(status, execution_order, created_at);

"""
