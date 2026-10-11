from __future__ import annotations

OPERATIONS_SCHEMA = """CREATE TABLE IF NOT EXISTS task_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    stage TEXT NOT NULL,
    message TEXT NOT NULL,
    progress_current INTEGER,
    progress_total INTEGER,
    actor_id TEXT REFERENCES users(id),
    data_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_task_events_task
ON task_events(task_id, id);

CREATE TABLE IF NOT EXISTS review_batches (
    id TEXT PRIMARY KEY,
    base_result_version_id TEXT NOT NULL
        REFERENCES classification_result_versions(id),
    result_id TEXT NOT NULL REFERENCES classification_results(id),
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft', 'published')),
    revision INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    published_version_id TEXT REFERENCES classification_result_versions(id),
    published_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_review_batches_base
ON review_batches(base_result_version_id, created_at DESC);

CREATE TABLE IF NOT EXISTS review_records (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    batch_id TEXT REFERENCES review_batches(id) ON DELETE CASCADE,
    base_result_version_id TEXT REFERENCES classification_result_versions(id),
    classification_key TEXT NOT NULL,
    comment TEXT NOT NULL,
    workflow_status TEXT NOT NULL DEFAULT 'pending',
    classification_json TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    updated_by TEXT REFERENCES users(id),
    updated_at TEXT NOT NULL,
    UNIQUE(batch_id, classification_key)
);
CREATE INDEX IF NOT EXISTS idx_review_records_status
ON review_records(workflow_status, updated_at DESC);

CREATE TABLE IF NOT EXISTS review_revisions (
    id TEXT PRIMARY KEY,
    review_record_id TEXT NOT NULL REFERENCES review_records(id),
    revision INTEGER NOT NULL,
    before_json TEXT NOT NULL,
    after_json TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    actor_id TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT,
    actor_id TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_entity
ON audit_logs(entity_type, entity_id, created_at DESC);
"""
