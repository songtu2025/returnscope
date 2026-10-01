from __future__ import annotations

import hashlib
import sqlite3

SEMANTIC_SCHEMA = """
CREATE TABLE IF NOT EXISTS classification_unit_semantics (
    result_version_id TEXT NOT NULL
        REFERENCES classification_result_versions(id) ON DELETE CASCADE,
    classification_key TEXT NOT NULL,
    semantic_index INTEGER NOT NULL,
    subject TEXT,
    label_code TEXT,
    part TEXT,
    opinion TEXT,
    evidence TEXT,
    PRIMARY KEY(result_version_id, classification_key, semantic_index)
);
"""
SEMANTIC_INSERT_SQL = """
INSERT INTO classification_unit_semantics(
    result_version_id, classification_key, semantic_index,
    subject, label_code, part, opinion, evidence
)
SELECT u.result_version_id, u.classification_key, unit.key,
       json_extract(unit.value, '$.subject'),
       json_extract(unit.value, '$.label_code'),
       json_extract(unit.value, '$.part'),
       json_extract(unit.value, '$.opinion'),
       json_extract(unit.value, '$.evidence')
FROM classification_units u
JOIN json_each(u.classification_json, '$.semantic_units') unit
"""
SEMANTIC_MIGRATION = "20261001_classification_unit_semantics"
SEMANTIC_MIGRATION_CHECKSUM = hashlib.sha256(
    (SEMANTIC_SCHEMA + SEMANTIC_INSERT_SQL).encode("utf-8")
).hexdigest()


def refresh_unit_semantics(
    connection: sqlite3.Connection, version_id: str | None = None
) -> None:
    """在调用方事务中投影原始语义，保留序号和重复项，不提前聚合反馈。"""
    where_sql = " WHERE result_version_id = ?" if version_id else ""
    params = (version_id,) if version_id else ()
    connection.execute("DELETE FROM classification_unit_semantics" + where_sql, params)
    connection.execute(
        SEMANTIC_INSERT_SQL + (" WHERE u.result_version_id = ?" if version_id else ""),
        params,
    )


def migrate_unit_semantics(connection: sqlite3.Connection) -> None:
    """首次升级回填存量，失败回滚投影及迁移记录，后续升级不重复解析。"""
    migration = connection.execute(
        "SELECT checksum FROM app_migrations WHERE migration_id = ?",
        (SEMANTIC_MIGRATION,),
    ).fetchone()
    if migration is not None:
        if migration[0] != SEMANTIC_MIGRATION_CHECKSUM:
            raise RuntimeError("分类语义明细迁移校验失败")
        return
    connection.execute("SAVEPOINT migrate_unit_semantics")
    try:
        connection.execute(SEMANTIC_SCHEMA)
        refresh_unit_semantics(connection)
        connection.execute(
            """
            INSERT INTO app_migrations(migration_id, checksum, status, applied_at)
            VALUES (?, ?, 'applied', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            """,
            (SEMANTIC_MIGRATION, SEMANTIC_MIGRATION_CHECKSUM),
        )
    except Exception:
        connection.execute("ROLLBACK TO migrate_unit_semantics")
        connection.execute("RELEASE migrate_unit_semantics")
        raise
    connection.execute("RELEASE migrate_unit_semantics")
