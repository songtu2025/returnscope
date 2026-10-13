from __future__ import annotations

DASHBOARD_SCHEMA = """CREATE TABLE IF NOT EXISTS analysis_dashboards (
    id TEXT PRIMARY KEY,
    deleted_at TEXT,
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
    cancelled_at TEXT,
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

"""
