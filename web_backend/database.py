from __future__ import annotations

import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_seen_at TEXT
);

CREATE TABLE IF NOT EXISTS user_model_preferences (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    connection_id TEXT NOT NULL REFERENCES api_connections(id),
    cheap_model TEXT,
    cheap_effort TEXT NOT NULL DEFAULT 'low',
    primary_model TEXT NOT NULL,
    primary_effort TEXT NOT NULL DEFAULT 'medium',
    secondary_model TEXT,
    secondary_effort TEXT NOT NULL DEFAULT 'high',
    cheap_audit_percent INTEGER NOT NULL DEFAULT 5,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_token_hash
ON sessions(token_hash);

CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('returns', 'products')),
    description TEXT NOT NULL DEFAULT '',
    current_version INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT
);

CREATE TABLE IF NOT EXISTS dataset_versions (
    id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    original_name TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    column_count INTEGER NOT NULL,
    schema_json TEXT NOT NULL,
    quality_json TEXT NOT NULL,
    change_note TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    UNIQUE(dataset_id, version)
);
CREATE INDEX IF NOT EXISTS idx_dataset_versions_dataset
ON dataset_versions(dataset_id, version DESC);

CREATE TABLE IF NOT EXISTS api_connections (
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

CREATE TABLE IF NOT EXISTS tasks (
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
    last_scheduled_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_owner_status
ON tasks(owner_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_status_created
ON tasks(status, created_at);

CREATE TABLE IF NOT EXISTS task_segments (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    segment_key TEXT NOT NULL,
    agent_key TEXT NOT NULL,
    agent_family TEXT NOT NULL,
    logic_version TEXT,
    taxonomy_version TEXT NOT NULL,
    model_policy_version TEXT,
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

CREATE TABLE IF NOT EXISTS classification_results (
    id TEXT PRIMARY KEY,
    source_task_id TEXT NOT NULL,
    source_segment_id TEXT NOT NULL UNIQUE,
    dataset_version_id TEXT NOT NULL REFERENCES dataset_versions(id),
    product_version_id TEXT NOT NULL REFERENCES dataset_versions(id),
    store_site TEXT,
    listing TEXT,
    agent_key TEXT NOT NULL,
    agent_family TEXT NOT NULL,
    logic_version TEXT,
    taxonomy_version TEXT NOT NULL,
    model_policy_version TEXT,
    claims_version TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_classification_results_created
ON classification_results(created_at DESC, id);
CREATE INDEX IF NOT EXISTS idx_classification_results_listing
ON classification_results(store_site, listing, created_at DESC);

CREATE TABLE IF NOT EXISTS classification_result_versions (
    id TEXT PRIMARY KEY,
    result_id TEXT NOT NULL REFERENCES classification_results(id) ON DELETE CASCADE,
    source_segment_id TEXT NOT NULL,
    version_no INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    quality_status TEXT NOT NULL
        CHECK(quality_status IN ('ready', 'review_required', 'unusable')),
    publish_status TEXT NOT NULL
        CHECK(publish_status IN ('publishing', 'published', 'failed')),
    unit_count INTEGER NOT NULL DEFAULT 0,
    record_count INTEGER NOT NULL DEFAULT 0,
    parent_version_id TEXT REFERENCES classification_result_versions(id),
    version_reason TEXT NOT NULL DEFAULT '',
    created_by TEXT REFERENCES users(id),
    created_at TEXT NOT NULL,
    published_at TEXT,
    UNIQUE(source_segment_id, version_no),
    UNIQUE(result_id, version_no)
);
CREATE INDEX IF NOT EXISTS idx_classification_versions_published
ON classification_result_versions(publish_status, published_at DESC, id);

CREATE TABLE IF NOT EXISTS classification_units (
    id TEXT PRIMARY KEY,
    result_version_id TEXT NOT NULL
        REFERENCES classification_result_versions(id) ON DELETE CASCADE,
    classification_key TEXT NOT NULL,
    reason TEXT,
    comment TEXT,
    classification_json TEXT NOT NULL,
    problem_labels_json TEXT NOT NULL DEFAULT '[]',
    processing_status TEXT NOT NULL,
    quality_status TEXT NOT NULL
        CHECK(quality_status IN ('ready', 'review_required', 'unusable', 'excluded')),
    record_count INTEGER NOT NULL DEFAULT 0,
    model_name TEXT,
    prompt_version TEXT,
    taxonomy_version TEXT,
    UNIQUE(result_version_id, classification_key)
);
CREATE INDEX IF NOT EXISTS idx_classification_units_quality
ON classification_units(result_version_id, quality_status, classification_key);

CREATE TABLE IF NOT EXISTS classification_unit_labels (
    result_version_id TEXT NOT NULL
        REFERENCES classification_result_versions(id) ON DELETE CASCADE,
    classification_key TEXT NOT NULL,
    label_kind TEXT NOT NULL,
    label_code TEXT NOT NULL,
    label_name TEXT,
    label_group TEXT,
    PRIMARY KEY(result_version_id, classification_key, label_kind, label_code)
);
CREATE INDEX IF NOT EXISTS idx_classification_labels_lookup
ON classification_unit_labels(result_version_id, label_kind, label_code);

CREATE TABLE IF NOT EXISTS classification_result_records (
    id TEXT PRIMARY KEY,
    result_version_id TEXT NOT NULL
        REFERENCES classification_result_versions(id) ON DELETE CASCADE,
    classification_key TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    return_date TEXT,
    order_id TEXT,
    store_site TEXT,
    listing TEXT,
    product_name TEXT,
    source_sku TEXT,
    matched_msku TEXT,
    product_sku TEXT,
    asin TEXT,
    fnsku TEXT,
    category_a TEXT,
    category_b TEXT,
    reason TEXT,
    comment TEXT,
    product_match_status TEXT NOT NULL,
    quality_status TEXT NOT NULL
        CHECK(quality_status IN ('ready', 'review_required', 'unusable', 'excluded')),
    UNIQUE(result_version_id, source_record_id)
);
CREATE INDEX IF NOT EXISTS idx_classification_records_listing
ON classification_result_records(result_version_id, listing, source_row);
CREATE INDEX IF NOT EXISTS idx_classification_records_source_row
ON classification_result_records(result_version_id, source_row, id);
CREATE INDEX IF NOT EXISTS idx_classification_records_order
ON classification_result_records(result_version_id, order_id, source_row);
CREATE INDEX IF NOT EXISTS idx_classification_records_source_sku
ON classification_result_records(result_version_id, source_sku, source_row);
CREATE INDEX IF NOT EXISTS idx_classification_records_matched_msku
ON classification_result_records(result_version_id, matched_msku, source_row);
CREATE INDEX IF NOT EXISTS idx_classification_records_product_sku
ON classification_result_records(result_version_id, product_sku, source_row);
CREATE INDEX IF NOT EXISTS idx_classification_records_product_name
ON classification_result_records(result_version_id, product_name, source_row);
CREATE INDEX IF NOT EXISTS idx_classification_records_asin
ON classification_result_records(result_version_id, asin, source_row);
CREATE INDEX IF NOT EXISTS idx_classification_records_quality
ON classification_result_records(result_version_id, quality_status, source_row);
CREATE INDEX IF NOT EXISTS idx_classification_records_unit
ON classification_result_records(
    result_version_id, classification_key, quality_status
);

CREATE TABLE IF NOT EXISTS analysis_dashboards (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'archived')),
    revision INTEGER NOT NULL DEFAULT 1,
    current_version_id TEXT,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analysis_dashboards_status
ON analysis_dashboards(status, updated_at DESC, id);

CREATE TABLE IF NOT EXISTS dashboard_dataset_versions (
    id TEXT PRIMARY KEY,
    dashboard_id TEXT NOT NULL
        REFERENCES analysis_dashboards(id) ON DELETE CASCADE,
    version_no INTEGER NOT NULL,
    filters_json TEXT NOT NULL DEFAULT '{}',
    source_snapshot_json TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    UNIQUE(dashboard_id, version_no)
);
CREATE INDEX IF NOT EXISTS idx_dashboard_datasets_dashboard
ON dashboard_dataset_versions(dashboard_id, version_no DESC);

CREATE TABLE IF NOT EXISTS dashboard_dataset_sources (
    dataset_version_id TEXT NOT NULL
        REFERENCES dashboard_dataset_versions(id) ON DELETE CASCADE,
    result_version_id TEXT NOT NULL
        REFERENCES classification_result_versions(id),
    store_site TEXT,
    listing TEXT,
    source_snapshot_json TEXT NOT NULL,
    PRIMARY KEY(dataset_version_id, result_version_id),
    UNIQUE(dataset_version_id, store_site, listing)
);
CREATE INDEX IF NOT EXISTS idx_dashboard_sources_result
ON dashboard_dataset_sources(result_version_id, dataset_version_id);

CREATE TABLE IF NOT EXISTS dashboard_versions (
    id TEXT PRIMARY KEY,
    dashboard_id TEXT NOT NULL
        REFERENCES analysis_dashboards(id) ON DELETE CASCADE,
    version_no INTEGER NOT NULL,
    dataset_version_id TEXT NOT NULL UNIQUE
        REFERENCES dashboard_dataset_versions(id),
    reason TEXT NOT NULL,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    UNIQUE(dashboard_id, version_no)
);
CREATE INDEX IF NOT EXISTS idx_dashboard_versions_dashboard
ON dashboard_versions(dashboard_id, version_no DESC);

CREATE TABLE IF NOT EXISTS ai_insight_reports (
    id TEXT PRIMARY KEY,
    dashboard_id TEXT NOT NULL
        REFERENCES analysis_dashboards(id) ON DELETE CASCADE,
    dashboard_version_id TEXT NOT NULL
        REFERENCES dashboard_versions(id) ON DELETE CASCADE,
    version_no INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK(status IN ('queued', 'running', 'completed', 'failed')),
    model_id TEXT NOT NULL REFERENCES api_models(id),
    model_key TEXT NOT NULL,
    resolved_model TEXT,
    config_version_id TEXT NOT NULL REFERENCES api_config_versions(id),
    reasoning_effort TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    evidence_hash TEXT,
    evidence_json TEXT,
    content_json TEXT,
    usage_json TEXT,
    metrics_json TEXT,
    error TEXT,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    UNIQUE(dashboard_id, version_no)
);
CREATE INDEX IF NOT EXISTS idx_ai_insight_reports_dashboard
ON ai_insight_reports(dashboard_id, version_no DESC);
CREATE INDEX IF NOT EXISTS idx_ai_insight_reports_status
ON ai_insight_reports(status, created_at);

CREATE TABLE IF NOT EXISTS ai_insight_report_versions (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE
        REFERENCES ai_insight_reports(id) ON DELETE CASCADE,
    dashboard_id TEXT NOT NULL
        REFERENCES analysis_dashboards(id) ON DELETE CASCADE,
    dashboard_version_id TEXT NOT NULL
        REFERENCES dashboard_versions(id) ON DELETE CASCADE,
    version_no INTEGER NOT NULL,
    published_at TEXT NOT NULL,
    UNIQUE(dashboard_id, version_no)
);
CREATE INDEX IF NOT EXISTS idx_ai_insight_report_versions_dashboard
ON ai_insight_report_versions(dashboard_id, version_no DESC);

CREATE TRIGGER IF NOT EXISTS trg_dashboard_current_version_insert
BEFORE INSERT ON analysis_dashboards
WHEN NEW.current_version_id IS NOT NULL
 AND NOT EXISTS (
     SELECT 1 FROM dashboard_versions version
     WHERE version.id = NEW.current_version_id
       AND version.dashboard_id = NEW.id
 )
BEGIN
    SELECT RAISE(ABORT, 'current_version_id must belong to dashboard');
END;

CREATE TRIGGER IF NOT EXISTS trg_dashboard_current_version_update
BEFORE UPDATE OF current_version_id ON analysis_dashboards
WHEN NEW.current_version_id IS NOT NULL
 AND NOT EXISTS (
     SELECT 1 FROM dashboard_versions version
     WHERE version.id = NEW.current_version_id
       AND version.dashboard_id = NEW.id
 )
BEGIN
    SELECT RAISE(ABORT, 'current_version_id must belong to dashboard');
END;

CREATE TABLE IF NOT EXISTS task_events (
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


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=30,
            isolation_level=None,
            factory=ClosingConnection,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(SCHEMA)
            user_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(users)").fetchall()
            }
            if "is_admin" not in user_columns:
                connection.execute(
                    "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"
                )
            config_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(api_config_versions)"
                ).fetchall()
            }
            if "change_note" not in config_columns:
                connection.execute(
                    """
                    ALTER TABLE api_config_versions
                    ADD COLUMN change_note TEXT NOT NULL DEFAULT ''
                    """
                )
            segment_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(task_segments)"
                ).fetchall()
            }
            if "classification_keys_json" not in segment_columns:
                connection.execute(
                    """
                    ALTER TABLE task_segments
                    ADD COLUMN classification_keys_json TEXT NOT NULL DEFAULT '[]'
                    """
                )
            if "execution_order" not in segment_columns:
                connection.execute(
                    """
                    ALTER TABLE task_segments
                    ADD COLUMN execution_order INTEGER NOT NULL DEFAULT 0
                    """
                )
                rows = connection.execute(
                    """
                    SELECT id, task_id FROM task_segments
                    ORDER BY task_id, created_at, segment_key
                    """
                ).fetchall()
                task_positions: dict[str, int] = {}
                for row in rows:
                    task_id = str(row["task_id"])
                    position = task_positions.get(task_id, 0) + 1
                    task_positions[task_id] = position
                    connection.execute(
                        "UPDATE task_segments SET execution_order = ? WHERE id = ?",
                        (position, row["id"]),
                    )
            for column_name in (
                "model_policy_version",
                "model_policy_json",
                "claims_version",
                "scope_json",
            ):
                if column_name not in segment_columns:
                    connection.execute(
                        f"ALTER TABLE task_segments ADD COLUMN {column_name} TEXT"
                    )
            segment_column_definitions = {
                "requested_action": "TEXT",
                "revision": "INTEGER NOT NULL DEFAULT 1",
                "retry_count": "INTEGER NOT NULL DEFAULT 0",
                "model_failures": "INTEGER NOT NULL DEFAULT 0",
                "heartbeat_at": "TEXT",
                "result_file_path": "TEXT",
                "result_json_path": "TEXT",
                "result_version": "INTEGER NOT NULL DEFAULT 0",
                "result_version_id": "TEXT",
                "result_publish_status": "TEXT",
                "result_quality_status": "TEXT",
                "result_published_at": "TEXT",
                "result_publish_error": "TEXT",
            }
            for column_name, definition in segment_column_definitions.items():
                if column_name not in segment_columns:
                    connection.execute(
                        f"ALTER TABLE task_segments ADD COLUMN {column_name} {definition}"
                    )
            version_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(classification_result_versions)"
                ).fetchall()
            }
            version_column_definitions = {
                "parent_version_id": "TEXT REFERENCES classification_result_versions(id)",
                "version_reason": "TEXT NOT NULL DEFAULT ''",
                "created_by": "TEXT REFERENCES users(id)",
            }
            for column_name, definition in version_column_definitions.items():
                if column_name not in version_columns:
                    connection.execute(
                        "ALTER TABLE classification_result_versions "
                        f"ADD COLUMN {column_name} {definition}"
                    )
            self._migrate_review_records(connection)
            self._repair_draft_review_batches(connection)
            self._migrate_excluded_quality_status(connection)
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_review_records_batch
                ON review_records(batch_id, updated_at DESC, id)
                """
            )
            task_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
            }
            task_column_definitions = {
                "pause_requested": "INTEGER NOT NULL DEFAULT 0",
                "max_parallel_segments": "INTEGER NOT NULL DEFAULT 3",
                "last_scheduled_at": "TEXT",
            }
            for column_name, definition in task_column_definitions.items():
                if column_name not in task_columns:
                    connection.execute(
                        f"ALTER TABLE tasks ADD COLUMN {column_name} {definition}"
                    )
            self._migrate_ai_insight_reports(connection)
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_task_segments_status_order
                ON task_segments(status, execution_order, created_at)
                """
            )
            connection.execute(
                """
                UPDATE classification_result_versions
                SET publish_status = 'failed'
                WHERE publish_status = 'publishing'
                """
            )
            connection.execute(
                """
                UPDATE task_segments
                SET result_publish_status = 'failed',
                    result_publish_error = COALESCE(
                        result_publish_error,
                        '服务重启时发现结果发布未完成，请重试发布'
                    )
                WHERE result_publish_status = 'publishing'
                  AND NOT EXISTS (
                      SELECT 1 FROM classification_result_versions v
                      WHERE v.source_segment_id = task_segments.id
                        AND v.publish_status = 'published'
                  )
                """
            )
            model_rows = connection.execute(
                """
                SELECT connection_id, primary_model AS model_key,
                       validation_status, validation_message, validated_at,
                       created_by, created_at
                FROM api_config_versions
                UNION ALL
                SELECT connection_id, cheap_model AS model_key,
                       validation_status, validation_message, validated_at,
                       created_by, created_at
                FROM api_config_versions
                WHERE cheap_model IS NOT NULL
                UNION ALL
                SELECT connection_id, secondary_model AS model_key,
                       validation_status, validation_message, validated_at,
                       created_by, created_at
                FROM api_config_versions
                WHERE secondary_model IS NOT NULL
                ORDER BY created_at
                """
            ).fetchall()
            for row in model_rows:
                model_id = f"model_{secrets.token_hex(8)}"
                connection.execute(
                    """
                    INSERT INTO api_models(
                        id, connection_id, model_key, display_name,
                        supported_efforts_json, active, validation_status,
                        validation_message, validated_at, created_by,
                        created_at, updated_by, updated_at
                    ) VALUES (?, ?, ?, ?, '["low","medium","high"]', 1,
                              ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(connection_id, model_key) DO UPDATE SET
                        validation_status = CASE
                            WHEN excluded.validation_status = 'validated'
                            THEN 'validated'
                            ELSE api_models.validation_status
                        END,
                        validation_message = CASE
                            WHEN excluded.validation_status = 'validated'
                            THEN excluded.validation_message
                            ELSE api_models.validation_message
                        END,
                        validated_at = CASE
                            WHEN excluded.validation_status = 'validated'
                            THEN excluded.validated_at
                            ELSE api_models.validated_at
                        END
                    """,
                    (
                        model_id,
                        row["connection_id"],
                        row["model_key"],
                        row["model_key"],
                        row["validation_status"],
                        row["validation_message"],
                        row["validated_at"],
                        row["created_by"],
                        row["created_at"],
                        row["created_by"],
                        row["created_at"],
                    ),
                )
            connection.execute("PRAGMA optimize")

    @staticmethod
    def _migrate_ai_insight_reports(connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(ai_insight_reports)"
            ).fetchall()
        }
        definitions = {
            "stage": "TEXT NOT NULL DEFAULT 'queued'",
            "technical_error": "TEXT",
            "parent_job_id": "TEXT REFERENCES ai_insight_reports(id)",
        }
        for column_name, definition in definitions.items():
            if column_name not in columns:
                connection.execute(
                    f"ALTER TABLE ai_insight_reports "
                    f"ADD COLUMN {column_name} {definition}"
                )
        connection.execute(
            """
            UPDATE ai_insight_reports
            SET stage = CASE status
                WHEN 'queued' THEN 'queued'
                WHEN 'running' THEN 'preparing_evidence'
                WHEN 'completed' THEN 'completed'
                WHEN 'failed' THEN 'failed'
                ELSE stage
            END
            WHERE stage IS NULL OR stage = ''
               OR (stage = 'queued' AND status != 'queued')
            """
        )
        connection.execute(
            """
            UPDATE ai_insight_reports
            SET technical_error = COALESCE(technical_error, error),
                error = '报告生成未完成，请稍后重试。失败尝试已保留，且不会占用报告版本号。'
            WHERE status = 'failed'
              AND error IS NOT NULL
              AND error != '报告生成未完成，请稍后重试。失败尝试已保留，且不会占用报告版本号。'
            """
        )
        completed_rows = connection.execute(
            """
            SELECT report.id, report.dashboard_id,
                   report.dashboard_version_id, report.completed_at,
                   report.created_at
            FROM ai_insight_reports report
            LEFT JOIN ai_insight_report_versions version
              ON version.job_id = report.id
            WHERE report.status = 'completed' AND version.id IS NULL
            ORDER BY report.dashboard_id,
                     COALESCE(report.completed_at, report.created_at),
                     report.id
            """
        ).fetchall()
        next_versions: dict[str, int] = {}
        for row in completed_rows:
            dashboard_id = str(row["dashboard_id"])
            if dashboard_id not in next_versions:
                next_versions[dashboard_id] = int(
                    connection.execute(
                        """
                        SELECT COALESCE(MAX(version_no), 0) + 1
                        FROM ai_insight_report_versions
                        WHERE dashboard_id = ?
                        """,
                        (dashboard_id,),
                    ).fetchone()[0]
                )
            version_no = next_versions[dashboard_id]
            next_versions[dashboard_id] += 1
            connection.execute(
                """
                INSERT INTO ai_insight_report_versions(
                    id, job_id, dashboard_id, dashboard_version_id,
                    version_no, published_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"insight_report_version_{secrets.token_hex(8)}",
                    row["id"],
                    dashboard_id,
                    row["dashboard_version_id"],
                    version_no,
                    row["completed_at"] or row["created_at"],
                ),
            )

    @staticmethod
    def _migrate_review_records(connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(review_records)").fetchall()
        }
        table_sql_row = connection.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name = 'review_records'
            """
        ).fetchone()
        table_sql = str(table_sql_row["sql"] or "") if table_sql_row else ""
        if "batch_id" in columns and "UNIQUE(task_id, classification_key)" not in table_sql:
            return

        foreign_keys_enabled = bool(
            connection.execute("PRAGMA foreign_keys").fetchone()[0]
        )
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("SAVEPOINT migrate_review_records")
        try:
            connection.execute(
                "ALTER TABLE review_revisions RENAME TO legacy_review_revisions"
            )
            connection.execute(
                "ALTER TABLE review_records RENAME TO legacy_review_records"
            )
            connection.execute(
                """
                CREATE TABLE review_records (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                batch_id TEXT REFERENCES review_batches(id) ON DELETE CASCADE,
                base_result_version_id TEXT
                    REFERENCES classification_result_versions(id),
                classification_key TEXT NOT NULL,
                comment TEXT NOT NULL,
                workflow_status TEXT NOT NULL DEFAULT 'pending',
                classification_json TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 1,
                updated_by TEXT REFERENCES users(id),
                updated_at TEXT NOT NULL,
                UNIQUE(batch_id, classification_key)
                )
                """
            )
            connection.execute(
                """
                INSERT INTO review_records(
                id, task_id, batch_id, base_result_version_id,
                classification_key, comment, workflow_status,
                classification_json, revision, updated_by, updated_at
                )
                SELECT id, task_id, NULL, NULL, classification_key, comment,
                       workflow_status, classification_json, revision,
                       updated_by, updated_at
                FROM legacy_review_records
                """
            )
            connection.execute(
                """
                CREATE TABLE review_revisions (
                id TEXT PRIMARY KEY,
                review_record_id TEXT NOT NULL REFERENCES review_records(id),
                revision INTEGER NOT NULL,
                before_json TEXT NOT NULL,
                after_json TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                actor_id TEXT NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO review_revisions(
                id, review_record_id, revision, before_json, after_json,
                note, actor_id, created_at
                )
                SELECT id, review_record_id, revision, before_json, after_json,
                       note, actor_id, created_at
                FROM legacy_review_revisions
                """
            )
            connection.execute("DROP TABLE legacy_review_revisions")
            connection.execute("DROP TABLE legacy_review_records")
            connection.execute(
                """
                CREATE INDEX idx_review_records_status
                ON review_records(workflow_status, updated_at DESC)
                """
            )
            connection.execute(
                """
                CREATE INDEX idx_review_records_batch
                ON review_records(batch_id, updated_at DESC, id)
                """
            )
        except Exception:
            connection.execute("ROLLBACK TO SAVEPOINT migrate_review_records")
            connection.execute("RELEASE SAVEPOINT migrate_review_records")
            raise
        else:
            connection.execute("RELEASE SAVEPOINT migrate_review_records")
        finally:
            if foreign_keys_enabled:
                connection.execute("PRAGMA foreign_keys = ON")

    @staticmethod
    def _repair_draft_review_batches(connection: sqlite3.Connection) -> None:
        missing_records = connection.execute(
            """
            SELECT b.id AS batch_id, b.base_result_version_id,
                   b.updated_at, result.source_task_id,
                   unit.classification_key, unit.comment,
                   unit.classification_json
            FROM review_batches b
            JOIN classification_results result ON result.id = b.result_id
            JOIN classification_units unit
              ON unit.result_version_id = b.base_result_version_id
            LEFT JOIN review_records review
              ON review.batch_id = b.id
             AND review.classification_key = unit.classification_key
            WHERE b.status = 'draft'
              AND unit.quality_status != 'ready'
              AND review.id IS NULL
            ORDER BY b.id, unit.classification_key
            """
        ).fetchall()
        if not missing_records:
            return
        connection.executemany(
            """
            INSERT INTO review_records(
                id, task_id, batch_id, base_result_version_id,
                classification_key, comment, workflow_status,
                classification_json, revision, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, 1, ?)
            """,
            [
                (
                    f"review_{secrets.token_hex(8)}",
                    row["source_task_id"],
                    row["batch_id"],
                    row["base_result_version_id"],
                    row["classification_key"],
                    str(row["comment"] or ""),
                    row["classification_json"],
                    row["updated_at"],
                )
                for row in missing_records
            ],
        )

    @staticmethod
    def _migrate_excluded_quality_status(
        connection: sqlite3.Connection,
    ) -> None:
        table_sql = {
            str(row["name"]): str(row["sql"] or "")
            for row in connection.execute(
                """
                SELECT name, sql FROM sqlite_master
                WHERE type = 'table'
                  AND name IN (
                      'classification_units',
                      'classification_result_records'
                  )
                """
            ).fetchall()
        }
        if all("'excluded'" in sql for sql in table_sql.values()):
            return

        foreign_keys_enabled = bool(
            connection.execute("PRAGMA foreign_keys").fetchone()[0]
        )
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("SAVEPOINT migrate_excluded_quality_status")
        try:
            if "'excluded'" not in table_sql.get("classification_units", ""):
                connection.execute(
                    "ALTER TABLE classification_units RENAME TO legacy_classification_units"
                )
                connection.execute("DROP INDEX idx_classification_units_quality")
                connection.execute(
                    """
                    CREATE TABLE classification_units (
                        id TEXT PRIMARY KEY,
                        result_version_id TEXT NOT NULL
                            REFERENCES classification_result_versions(id)
                            ON DELETE CASCADE,
                        classification_key TEXT NOT NULL,
                        reason TEXT,
                        comment TEXT,
                        classification_json TEXT NOT NULL,
                        problem_labels_json TEXT NOT NULL DEFAULT '[]',
                        processing_status TEXT NOT NULL,
                        quality_status TEXT NOT NULL CHECK(
                            quality_status IN (
                                'ready', 'review_required', 'unusable', 'excluded'
                            )
                        ),
                        record_count INTEGER NOT NULL DEFAULT 0,
                        model_name TEXT,
                        prompt_version TEXT,
                        taxonomy_version TEXT,
                        UNIQUE(result_version_id, classification_key)
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO classification_units
                    SELECT * FROM legacy_classification_units
                    """
                )
                connection.execute("DROP TABLE legacy_classification_units")
                connection.execute(
                    """
                    CREATE INDEX idx_classification_units_quality
                    ON classification_units(
                        result_version_id, quality_status, classification_key
                    )
                    """
                )
            if "'excluded'" not in table_sql.get(
                "classification_result_records",
                "",
            ):
                connection.execute(
                    """
                    ALTER TABLE classification_result_records
                    RENAME TO legacy_classification_result_records
                    """
                )
                record_indexes = [
                    "idx_classification_records_listing",
                    "idx_classification_records_source_row",
                    "idx_classification_records_order",
                    "idx_classification_records_source_sku",
                    "idx_classification_records_matched_msku",
                    "idx_classification_records_product_sku",
                    "idx_classification_records_product_name",
                    "idx_classification_records_asin",
                    "idx_classification_records_quality",
                    "idx_classification_records_unit",
                ]
                for index_name in record_indexes:
                    connection.execute(f"DROP INDEX {index_name}")
                connection.execute(
                    """
                    CREATE TABLE classification_result_records (
                        id TEXT PRIMARY KEY,
                        result_version_id TEXT NOT NULL
                            REFERENCES classification_result_versions(id)
                            ON DELETE CASCADE,
                        classification_key TEXT NOT NULL,
                        source_record_id TEXT NOT NULL,
                        source_row INTEGER NOT NULL,
                        return_date TEXT,
                        order_id TEXT,
                        store_site TEXT,
                        listing TEXT,
                        product_name TEXT,
                        source_sku TEXT,
                        matched_msku TEXT,
                        product_sku TEXT,
                        asin TEXT,
                        fnsku TEXT,
                        category_a TEXT,
                        category_b TEXT,
                        reason TEXT,
                        comment TEXT,
                        product_match_status TEXT NOT NULL,
                        quality_status TEXT NOT NULL CHECK(
                            quality_status IN (
                                'ready', 'review_required', 'unusable', 'excluded'
                            )
                        ),
                        UNIQUE(result_version_id, source_record_id)
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO classification_result_records
                    SELECT * FROM legacy_classification_result_records
                    """
                )
                connection.execute(
                    "DROP TABLE legacy_classification_result_records"
                )
                record_index_columns = {
                    "listing": "listing, source_row",
                    "source_row": "source_row, id",
                    "order": "order_id, source_row",
                    "source_sku": "source_sku, source_row",
                    "matched_msku": "matched_msku, source_row",
                    "product_sku": "product_sku, source_row",
                    "product_name": "product_name, source_row",
                    "asin": "asin, source_row",
                    "quality": "quality_status, source_row",
                    "unit": "classification_key, quality_status",
                }
                for suffix, columns in record_index_columns.items():
                    connection.execute(
                        "CREATE INDEX idx_classification_records_"
                        f"{suffix} ON classification_result_records("
                        f"result_version_id, {columns})"
                    )
        except Exception:
            connection.execute("ROLLBACK TO SAVEPOINT migrate_excluded_quality_status")
            connection.execute("RELEASE SAVEPOINT migrate_excluded_quality_status")
            raise
        else:
            connection.execute("RELEASE SAVEPOINT migrate_excluded_quality_status")
        finally:
            if foreign_keys_enabled:
                connection.execute("PRAGMA foreign_keys = ON")

    @contextmanager
    def transaction(self, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
