from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any

from return_semantics.schemas import TaxonomyConfig
from web_backend.classification_results.record_groups import assemble_record_groups
from web_backend.classification_results.result_export import (
    feedback_export_row,
    semantic_export_rows,
    source_export_rows,
)
from web_backend.classification_results.result_workbook import result_workbook
from web_backend.database import Database
from web_backend.result_hierarchy import feedback_group_key_sql, result_taxonomy


class _ClassificationResultDownload:
    database: Database

    if TYPE_CHECKING:

        def _get_version_with_connection(
            self, connection: sqlite3.Connection, version_id: str
        ) -> dict[str, Any]: ...

        @staticmethod
        def _records_select() -> str: ...

        @staticmethod
        def _serialize_record(value: dict[str, Any]) -> dict[str, Any]: ...

        @staticmethod
        def _enrich_record(
            value: dict[str, Any],
            taxonomy: TaxonomyConfig | None,
        ) -> dict[str, Any]: ...

    def download(self, version_id: str) -> tuple[bytes, str]:
        snapshot = self.capture_export([version_id])
        return self.snapshot_workbook(snapshot), snapshot[0]["filename"]

    def download_versions(self, version_ids: list[str]) -> bytes:
        return self.snapshot_workbook(self.capture_export(version_ids))

    def capture_export(self, version_ids: list[str]) -> list[dict[str, Any]]:
        """在同一个读事务中固定原文、语义和产品资料，写文件时不占事务。"""
        snapshot = []
        with self.database.transaction() as connection:
            for version_id in version_ids:
                version = self._get_version_with_connection(connection, version_id)
                taxonomy = result_taxonomy(connection, version_id)
                snapshot.append(
                    {
                        "version_id": version_id,
                        "filename": f"classification-{version['listing'] or version['result_id']}-v{version['version']}.xlsx",
                        "taxonomy": taxonomy.model_dump(mode="json")
                        if taxonomy
                        else None,
                        "rows": [
                            dict(row)
                            for row in self._export_records(version_id, connection)
                        ],
                    }
                )
        return snapshot

    def snapshot_workbook(self, snapshot: list[dict[str, Any]]) -> bytes:
        output: list[dict[str, Any]] = []
        semantics = []
        sources = []
        for version in snapshot:
            rows = version["rows"]
            source_records = {row["source_record_id"]: row for row in rows}
            taxonomy = (
                TaxonomyConfig.model_validate(version["taxonomy"])
                if version["taxonomy"]
                else None
            )

            def prepare_record(
                row: dict[str, Any], taxonomy: TaxonomyConfig | None = taxonomy
            ) -> dict[str, Any]:
                return self._enrich_record(self._serialize_record(row), taxonomy)

            groups = assemble_record_groups(rows, prepare_record)
            for group in groups:
                feedback_id = f"F{len(output) + 1:06d}"
                details = semantic_export_rows(group["record"], feedback_id)
                semantics.extend(details)
                output.append(feedback_export_row(group, feedback_id, details))
                sources.extend(
                    source_export_rows(
                        [
                            source_records[member["source_record_id"]]
                            for member in group["members"]
                        ],
                        feedback_id,
                    )
                )
        return result_workbook(output, semantics, sources)

    def _export_records(
        self, version_id: str, connection: sqlite3.Connection | None = None
    ) -> list[Any]:
        if connection is None:
            with self.database.connect() as owned:
                return self._export_records(version_id, owned)
        return connection.execute(
            f"""
                SELECT item.*, {feedback_group_key_sql("item")} AS display_key,
                       COUNT(*) OVER (PARTITION BY {feedback_group_key_sql("item")}) AS member_count
                FROM ({self._records_select()} WHERE r.result_version_id = ?) item
                ORDER BY item.source_row ASC, item.id ASC
                """,
            (version_id,),
        ).fetchall()
