from __future__ import annotations

RESULT_SCHEMA = """CREATE TABLE IF NOT EXISTS classification_results (
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

"""
