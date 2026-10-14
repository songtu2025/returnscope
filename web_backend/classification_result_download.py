from __future__ import annotations

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
from web_backend.result_hierarchy import feedback_group_key_sql


class _ClassificationResultDownload:
    database: Database

    if TYPE_CHECKING:

        def get(self, version_id: str) -> dict[str, Any]: ...

        def taxonomy(self, version_id: str) -> TaxonomyConfig | None: ...

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
        version = self.get(version_id)
        filename = (
            f"classification-{version['listing'] or version['result_id']}"
            f"-v{version['version']}.xlsx"
        )
        return self._download_versions([version]), filename

    def download_versions(self, version_ids: list[str]) -> bytes:
        return self._download_versions(
            [self.get(version_id) for version_id in version_ids]
        )

    def _download_versions(self, versions: list[dict[str, Any]]) -> bytes:
        output: list[dict[str, Any]] = []
        semantics = []
        sources = []
        for version in versions:
            version_id = version["version_id"]
            rows = self._export_records(version_id)
            source_records = {row["source_record_id"]: row for row in rows}
            taxonomy = self.taxonomy(version_id)

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

    def _export_records(self, version_id: str) -> list[Any]:
        with self.database.connect() as connection:
            return connection.execute(
                f"""
                SELECT item.*, {feedback_group_key_sql("item")} AS display_key,
                       COUNT(*) OVER (PARTITION BY {feedback_group_key_sql("item")}) AS member_count
                FROM ({self._records_select()} WHERE r.result_version_id = ?) item
                ORDER BY item.source_row ASC, item.id ASC
                """,
                (version_id,),
            ).fetchall()
