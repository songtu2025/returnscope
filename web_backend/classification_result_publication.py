from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from return_semantics.data import ReturnDataset
from return_semantics.schemas import TaxonomyConfig, ValidatedClassification
from web_backend.classification_results.publication_preparation import (
    prepare_publication,
)
from web_backend.classification_results.publication_units import insert_units
from web_backend.common import json_text, new_id
from web_backend.database import Database
from web_backend.security import utc_now


class ClassificationResultNotFound(ValueError):
    pass


class ResultPublicationError(RuntimeError):
    pass


class ResultPublicationConflict(ResultPublicationError):
    pass


@dataclass(frozen=True, kw_only=True)
class SegmentPublicationState:
    """保存一次发布需写回的片段状态，与分类结果内容分开传递。"""

    task_id: str
    segment_id: str
    segment_status: str
    progress_total: int
    model_calls: int
    cache_hits: int
    checkpoint_path: str
    legacy_result_version: int
    model_failures: int = 0


class _ClassificationResultPublication:
    database: Database

    def mark_publish_failed(
        self,
        task_id: str,
        segment_id: str,
        error: str,
    ) -> None:
        message = error[:500]
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE task_segments
                SET result_publish_status = 'failed',
                    result_publish_error = ?, revision = revision + 1
                WHERE id = ? AND task_id = ? AND result_version_id IS NULL
                """,
                (message, segment_id, task_id),
            )
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, data_json, created_at
                ) VALUES (?, 'result_publish_failed', '生成结果',
                          'Listing 分类结果发布失败', ?, ?)
                """,
                (
                    task_id,
                    json_text({"segment_id": segment_id, "error": message}),
                    now,
                ),
            )

    def attach_legacy_file(
        self,
        segment_id: str,
        output_path: str,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE task_segments SET result_file_path = ?
                WHERE id = ? AND result_publish_status = 'published'
                """,
                (output_path, segment_id),
            )

    def record_legacy_export_error(
        self,
        task_id: str,
        segment_id: str,
        error: str,
    ) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, data_json, created_at
                ) VALUES (?, 'legacy_export_failed', '生成结果',
                          '兼容 Excel 生成失败，数据库结果仍可查看和下载', ?, ?)
                """,
                (
                    task_id,
                    json_text({"segment_id": segment_id, "error": error[:500]}),
                    now,
                ),
            )

    def _prepare_publication(
        self,
        dataset: ReturnDataset,
        results: dict[str, ValidatedClassification],
        taxonomy: TaxonomyConfig,
    ) -> dict[str, Any]:
        return prepare_publication(dataset, results, taxonomy)

    @staticmethod
    def _content_hash(
        dataset_version_id: str,
        product_version_id: str,
        units: list[dict[str, Any]],
        records: list[dict[str, Any]],
    ) -> str:
        hasher = hashlib.sha256()
        hasher.update(f"{dataset_version_id}\x1f{product_version_id}\n".encode("utf-8"))
        for values in (units, records):
            for value in values:
                canonical = json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                hasher.update(canonical.encode("utf-8"))
                hasher.update(b"\n")
        return hasher.hexdigest()

    @staticmethod
    def _insert_units(
        connection: Any,
        version_id: str,
        units: list[dict[str, Any]],
        labels: list[dict[str, Any]],
    ) -> None:
        insert_units(connection, version_id, units, labels)

    @staticmethod
    def _insert_records(
        connection: Any,
        version_id: str,
        dataset_version_id: str,
        records: list[dict[str, Any]],
    ) -> None:
        connection.executemany(
            """
            INSERT INTO classification_result_records(
                id, result_version_id, classification_key,
                source_record_id, source_row, source_origin_id, return_date, order_id,
                store_site, listing, product_name, source_sku,
                matched_msku, product_sku, asin, fnsku, category_a,
                category_b, reason, comment, product_match_status,
                quality_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?)
            """,
            [
                (
                    new_id("classification_record"),
                    version_id,
                    value["classification_key"],
                    f"{dataset_version_id}:{value['source_row']}",
                    value["source_row"],
                    value.get("source_origin_id"),
                    value["return_date"],
                    value["order_id"],
                    value["store_site"],
                    value["listing"],
                    value["product_name"],
                    value["source_sku"],
                    value["matched_msku"],
                    value["product_sku"],
                    value["asin"],
                    value["fnsku"],
                    value["category_a"],
                    value["category_b"],
                    value["reason"],
                    value["comment"],
                    value["product_match_status"],
                    value["quality_status"],
                )
                for value in records
            ],
        )

    def _published_version_id(self, segment_id: str) -> str:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id FROM classification_result_versions
                WHERE source_segment_id = ? AND publish_status = 'published'
                ORDER BY version_no DESC LIMIT 1
                """,
                (segment_id,),
            ).fetchone()
        if row is None:
            raise ResultPublicationError("结果发布事务没有生成可用版本")
        return str(row["id"])
