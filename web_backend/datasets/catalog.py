from __future__ import annotations

import builtins
from typing import Any

from web_backend.common import json_value, list_audit
from web_backend.database import Database
from web_backend.dataset_files import (
    _return_source_key,
    _return_source_name,
)

_DATASET_SELECT = """
            SELECT d.*, u.display_name AS creator_name,
                   (SELECT COUNT(DISTINCT task.id)
                    FROM dataset_versions referenced_version
                    JOIN tasks task
                      ON task.dataset_version_id = referenced_version.id
                      OR task.product_version_id = referenced_version.id
                    WHERE referenced_version.dataset_id = d.id
                   ) AS task_reference_count,
                   v.id AS version_id, v.original_name, v.row_count,
                   v.column_count, v.size_bytes, v.schema_json,
                   v.quality_json, v.created_at AS version_created_at
            FROM datasets d
            JOIN users u ON u.id = d.created_by
            LEFT JOIN dataset_versions v
              ON v.dataset_id = d.id AND v.version = d.current_version
"""

_DATASET_VERSIONS_SQL = """
                    SELECT v.*, u.display_name AS creator_name
                    FROM dataset_versions v
                    JOIN users u ON u.id = v.created_by
                    WHERE v.dataset_id = ?
                    ORDER BY v.version DESC
                    """

_DATASET_IMPORTS_SQL = """
                    SELECT i.*, u.display_name AS creator_name
                    FROM dataset_imports i
                    JOIN users u ON u.id = i.created_by
                    WHERE i.dataset_id = ?
                    ORDER BY i.created_at DESC, i.id DESC
                    """


class _DatasetCatalog:
    database: Database

    def list(
        self,
        kind: str | None = None,
        usage_scope: str | None = None,
    ) -> list[dict[str, Any]]:
        query = _DATASET_SELECT + " WHERE d.archived_at IS NULL"
        params: list[object] = []
        if kind:
            query += " AND d.kind = ?"
            params.append(kind)
        if usage_scope:
            query += " AND d.usage_scope = ?"
            params.append(usage_scope)
        query += " ORDER BY d.updated_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._serialize(dict(row)) for row in rows]

    def get(
        self,
        dataset_id: str,
        include: set[str] | None = None,
    ) -> dict[str, Any] | None:
        requested = {"versions", "imports", "audit"} if include is None else include
        with self.database.connect() as connection:
            row = connection.execute(
                _DATASET_SELECT + " WHERE d.id = ? AND d.archived_at IS NULL",
                (dataset_id,),
            ).fetchone()
            if row is None:
                return None
            versions = (
                connection.execute(
                    _DATASET_VERSIONS_SQL,
                    (dataset_id,),
                ).fetchall()
                if "versions" in requested
                else []
            )
            imports = (
                connection.execute(
                    _DATASET_IMPORTS_SQL,
                    (dataset_id,),
                ).fetchall()
                if "imports" in requested
                else []
            )
        item = self._serialize(dict(row))
        if "versions" in requested:
            item["versions"] = [
                self._serialize_version(dict(value)) for value in versions
            ]
        if "imports" in requested:
            item["imports"] = [self._serialize_import(dict(value)) for value in imports]
        if "audit" in requested:
            item["audit"] = list_audit(self.database, "dataset", dataset_id)
        return item

    def list_versions(self, kind: str | None = None) -> builtins.list[dict[str, Any]]:
        query = """
            SELECT v.*, d.name AS dataset_name, d.kind, d.current_version,
                   d.source_key, d.usage_scope,
                   u.display_name AS creator_name
            FROM dataset_versions v
            JOIN datasets d ON d.id = v.dataset_id
            JOIN users u ON u.id = v.created_by
            WHERE d.archived_at IS NULL
        """
        params: tuple[object, ...] = ()
        if kind:
            query += " AND d.kind = ?"
            params = (kind,)
        query += " ORDER BY v.created_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        output = []
        for row in rows:
            item = self._serialize_version(dict(row))
            item["version_id"] = item["id"]
            output.append(item)
        return output

    def version_file(
        self,
        dataset_id: str,
        version: int | None = None,
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT v.file_path, v.original_name, v.content_type, v.version
                FROM dataset_versions v
                JOIN datasets d ON d.id = v.dataset_id
                WHERE v.dataset_id = ? AND d.archived_at IS NULL
                  AND v.version = COALESCE(?, d.current_version)
                """,
                (dataset_id, version),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _serialize(item: dict[str, Any]) -> dict[str, Any]:
        _decode_metadata(item)
        _return_source_fields(item, "name")
        return item

    @staticmethod
    def _serialize_version(item: dict[str, Any]) -> dict[str, Any]:
        item.pop("file_path", None)
        _decode_metadata(item)
        _return_source_fields(item, "dataset_name")
        return item

    @staticmethod
    def _serialize_import(item: dict[str, Any]) -> dict[str, Any]:
        item.pop("raw_file_path", None)
        _decode_metadata(item)
        return item


def _decode_metadata(item: dict[str, Any]) -> None:
    item["schema"] = json_value(item.pop("schema_json", None), [])
    item["quality"] = json_value(item.pop("quality_json", None), {})


def _return_source_fields(item: dict[str, Any], name_field: str) -> None:
    if item.get("kind") == "returns":
        stores = item["quality"].get("stores", [])
        if not item.get("source_key"):
            item["source_key"] = _return_source_key(stores)
        item["source_name"] = (
            _return_source_name(stores, "")
            if stores
            else str(item.get(name_field) or "未命名用户反馈数据")
        )
