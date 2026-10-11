from __future__ import annotations

CORE_SCHEMA = """
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

"""
