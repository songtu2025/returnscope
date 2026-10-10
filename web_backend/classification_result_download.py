from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, Any

import pandas as pd

from return_semantics.schemas import TaxonomyConfig
from web_backend.classification_results.result_export import (
    classification_export_row,
    semantic_export_rows,
)
from web_backend.database import Database


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
        output = []
        semantics = []
        for version in versions:
            version_id = version["version_id"]
            rows = self._export_records(version_id)
            taxonomy = self.taxonomy(version_id)
            for row in rows:
                item = self._enrich_record(self._serialize_record(dict(row)), taxonomy)
                semantics.extend(semantic_export_rows(item, version))
                output.append(classification_export_row(item))
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            pd.DataFrame(output).to_excel(writer, sheet_name="分类结果", index=False)
            pd.DataFrame(semantics).to_excel(writer, sheet_name="语义层级", index=False)
        return buffer.getvalue()

    def _export_records(self, version_id: str) -> list[Any]:
        with self.database.connect() as connection:
            return connection.execute(
                f"""
                {self._records_select()}
                WHERE r.result_version_id = ?
                ORDER BY r.source_row ASC, r.id ASC
                """,
                (version_id,),
            ).fetchall()
