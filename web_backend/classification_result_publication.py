from __future__ import annotations

import hashlib
import json
from typing import Any

from return_semantics.data import ReturnDataset
from return_semantics.schemas import TaxonomyConfig, ValidatedClassification
from return_semantics.semantic_review import requires_system_rerun
from web_backend.classification_result_payload import (
    _classification_quality,
    _nullable_text,
    _prepare_classification_payload,
)
from web_backend.common import json_text, new_id
from web_backend.database import Database
from web_backend.security import utc_now


class ClassificationResultNotFound(ValueError):
    pass


class ResultPublicationError(RuntimeError):
    pass


class ResultPublicationConflict(ResultPublicationError):
    pass


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
        label_map = {label.code: label for label in taxonomy.labels}
        comments = dataset.unique_comments.set_index("classification_key")
        units: list[dict[str, Any]] = []
        labels: list[dict[str, Any]] = []
        quality_by_key: dict[str, str] = {}
        for key in sorted(results):
            result = results[key]
            source = comments.loc[key]
            processing_status = result.status.value
            classification = _prepare_classification_payload(
                result.model_dump(mode="json"),
                taxonomy,
                processing_status,
                include_api_fields=False,
            )
            quality_status = _classification_quality(
                result,
                str(classification["semantic_disposition"]),
                source_text=str(source.get("comment_normalized") or ""),
                taxonomy=taxonomy,
            )
            classification.pop("semantic_disposition", None)
            for semantic_unit in classification.get("semantic_units", []):
                semantic_unit.pop("label_code_path", None)
                semantic_unit.pop("label_path", None)
            quality_by_key[key] = quality_status
            units.append(
                {
                    "classification_key": key,
                    "reason": _nullable_text(source.get("reason")),
                    "comment": _nullable_text(source.get("comment_normalized")),
                    "classification": classification,
                    "problem_labels": list(result.problem_label_codes),
                    "processing_status": processing_status,
                    "quality_status": quality_status,
                    "record_count": int(source.get("record_count", 0)),
                    "model_name": result.model_name,
                    "prompt_version": result.prompt_version,
                    "taxonomy_version": result.taxonomy_version,
                }
            )
            for kind, codes in (
                ("problem", result.problem_label_codes),
                ("positive", result.positive_label_codes),
                ("primary", result.primary_label_codes),
            ):
                for code in sorted(set(codes)):
                    label = label_map.get(code)
                    labels.append(
                        {
                            "classification_key": key,
                            "label_kind": kind,
                            "label_code": code,
                            "label_name": label.name if label else None,
                            "label_group": label.group if label else None,
                        }
                    )

        selected = dataset.records.loc[
            dataset.records["classification_key"].isin(results)
        ].copy()
        records: list[dict[str, Any]] = []
        for row in selected.sort_values("source_row").to_dict(orient="records"):
            classification_key = str(row["classification_key"])
            records.append(
                {
                    "classification_key": classification_key,
                    "source_row": int(row["source_row"]),
                    "source_origin_id": _nullable_text(row.get("source-origin-id")),
                    "return_date": _nullable_text(row.get("return-date")),
                    "order_id": _nullable_text(row.get("order-id")),
                    "store_site": _nullable_text(row.get("store")),
                    "listing": _nullable_text(row.get("listing")),
                    "product_name": _nullable_text(row.get("product_name")),
                    "source_sku": _nullable_text(row.get("source_sku")),
                    "matched_msku": _nullable_text(row.get("matched_msku")),
                    "product_sku": _nullable_text(row.get("product_sku")),
                    "asin": _nullable_text(row.get("asin")),
                    "fnsku": _nullable_text(row.get("fnsku")),
                    "category_a": _nullable_text(row.get("category_a")),
                    "category_b": _nullable_text(row.get("category_b")),
                    "reason": _nullable_text(row.get("reason")),
                    "comment": _nullable_text(row.get("comment_raw")),
                    "product_match_status": str(
                        row.get("product_match_status") or "unmatched"
                    ),
                    "quality_status": quality_by_key[classification_key],
                }
            )
        scopes = {(value["store_site"], value["listing"]) for value in records}
        store_site, listing = next(iter(scopes)) if len(scopes) == 1 else (None, None)
        return {
            "units": units,
            "labels": labels,
            "records": records,
            "store_site": store_site,
            "listing": listing,
        }

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
        connection.executemany(
            """
            INSERT INTO classification_units(
                id, result_version_id, classification_key, reason, comment,
                classification_json, problem_labels_json,
                system_rerun_required, processing_status, quality_status, record_count,
                model_name, prompt_version, taxonomy_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    new_id("classification_unit"),
                    version_id,
                    value["classification_key"],
                    value["reason"],
                    value["comment"],
                    json_text(value["classification"]),
                    json_text(value["problem_labels"]),
                    int(
                        requires_system_rerun(
                            value["classification"],
                            str(value["comment"] or ""),
                            processing_status=str(value["processing_status"] or ""),
                        )
                    ),
                    value["processing_status"],
                    value["quality_status"],
                    value["record_count"],
                    value["model_name"],
                    value["prompt_version"],
                    value["taxonomy_version"],
                )
                for value in units
            ],
        )
        connection.executemany(
            """
            INSERT INTO classification_unit_labels(
                result_version_id, classification_key, label_kind,
                label_code, label_name, label_group
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    version_id,
                    value["classification_key"],
                    value["label_kind"],
                    value["label_code"],
                    value["label_name"],
                    value["label_group"],
                )
                for value in labels
            ],
        )

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
