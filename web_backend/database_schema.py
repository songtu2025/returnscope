from __future__ import annotations

SCHEMA = """
CREATE TABLE IF NOT EXISTS app_migrations (
    migration_id TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('applied', 'baselined')),
    applied_at TEXT NOT NULL
);

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
    source_key TEXT,
    usage_scope TEXT NOT NULL DEFAULT 'managed',
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
CREATE INDEX IF NOT EXISTS idx_dataset_versions_sha
ON dataset_versions(sha256);

CREATE TABLE IF NOT EXISTS dataset_imports (
    id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    resulting_version_id TEXT NOT NULL REFERENCES dataset_versions(id),
    mode TEXT NOT NULL CHECK(mode IN ('analyze_only', 'create', 'append', 'replace')),
    raw_file_path TEXT NOT NULL,
    original_name TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    raw_sha256 TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    column_count INTEGER NOT NULL,
    schema_json TEXT NOT NULL,
    quality_json TEXT NOT NULL,
    source_key TEXT,
    imported_row_count INTEGER NOT NULL DEFAULT 0,
    skipped_row_count INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dataset_imports_dataset
ON dataset_imports(dataset_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_dataset_imports_sha
ON dataset_imports(raw_sha256, dataset_id);
CREATE INDEX IF NOT EXISTS idx_dataset_imports_result_version
ON dataset_imports(resulting_version_id);

CREATE TABLE IF NOT EXISTS dataset_import_staging (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    temp_path TEXT NOT NULL,
    original_name TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    inspection_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_dataset_import_staging_expiry
ON dataset_import_staging(expires_at);

CREATE TABLE IF NOT EXISTS classification_standards (
    id TEXT PRIMARY KEY,
    standard_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active', 'inactive')),
    current_version_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS classification_standard_versions (
    id TEXT PRIMARY KEY,
    standard_id TEXT NOT NULL
        REFERENCES classification_standards(id) ON DELETE CASCADE,
    version_no INTEGER NOT NULL,
    version_key TEXT NOT NULL,
    logic_version TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    model_policy_version TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    version_reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK(status IN ('published', 'inactive')),
    created_at TEXT NOT NULL,
    published_at TEXT NOT NULL,
    UNIQUE(standard_id, version_no),
    UNIQUE(standard_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_classification_standard_versions_standard
ON classification_standard_versions(standard_id, version_no DESC);

CREATE TABLE IF NOT EXISTS classification_standard_drafts (
    id TEXT PRIMARY KEY,
    standard_id TEXT NOT NULL UNIQUE
        REFERENCES classification_standards(id) ON DELETE CASCADE,
    base_version_id TEXT NOT NULL
        REFERENCES classification_standard_versions(id),
    snapshot_json TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    validation_json TEXT NOT NULL DEFAULT '{"blocking":[],"warnings":[]}',
    change_reason TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_by TEXT NOT NULL REFERENCES users(id),
    updated_at TEXT NOT NULL
);

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
    standard_version_id TEXT REFERENCES classification_standard_versions(id),
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
    system_rerun_required INTEGER NOT NULL DEFAULT 0
        CHECK(system_rerun_required IN (0, 1)),
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
    source_origin_id TEXT,
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

CREATE TABLE IF NOT EXISTS classification_standard_validation_runs (
    id TEXT PRIMARY KEY,
    standard_id TEXT NOT NULL REFERENCES classification_standards(id),
    draft_id TEXT NOT NULL,
    draft_revision INTEGER NOT NULL,
    base_version_id TEXT NOT NULL REFERENCES classification_standard_versions(id),
    source_result_version_id TEXT NOT NULL,
    config_version_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK(status IN ('queued', 'running', 'completed', 'failed')),
    stage TEXT NOT NULL DEFAULT 'queued',
    sample_size INTEGER NOT NULL,
    processed_count INTEGER NOT NULL DEFAULT 0,
    changed_count INTEGER NOT NULL DEFAULT 0,
    unknown_count INTEGER NOT NULL DEFAULT 0,
    review_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    snapshot_json TEXT NOT NULL,
    source_json TEXT NOT NULL,
    sample_json TEXT NOT NULL,
    result_json TEXT NOT NULL DEFAULT '[]',
    summary_json TEXT NOT NULL DEFAULT '{}',
    usage_json TEXT NOT NULL DEFAULT '{}',
    metrics_json TEXT NOT NULL DEFAULT '{}',
    model_names_json TEXT NOT NULL DEFAULT '[]',
    error TEXT,
    approved_by TEXT REFERENCES users(id),
    approved_at TEXT,
    approval_note TEXT NOT NULL DEFAULT '',
    published_version_id TEXT REFERENCES classification_standard_versions(id),
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_standard_validation_runs_draft
ON classification_standard_validation_runs(
    draft_id, draft_revision, created_at DESC
);
CREATE INDEX IF NOT EXISTS idx_standard_validation_runs_status
ON classification_standard_validation_runs(status, created_at);

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

CREATE TABLE IF NOT EXISTS ai_insight_issue_decisions (
    report_id TEXT NOT NULL
        REFERENCES ai_insight_reports(id) ON DELETE CASCADE,
    issue_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'ignored', 'watching', 'verify')),
    updated_by TEXT NOT NULL REFERENCES users(id),
    updated_at TEXT NOT NULL,
    PRIMARY KEY(report_id, issue_id)
);
CREATE INDEX IF NOT EXISTS idx_ai_insight_issue_decisions_status
ON ai_insight_issue_decisions(report_id, status, updated_at DESC);

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
