from __future__ import annotations

import hashlib
import json
from io import BytesIO
from typing import Any

import pandas as pd

from return_semantics.data import ReturnDataset
from return_semantics.exporter import REVIEW_STATUSES
from return_semantics.schemas import (
    ProcessingStatus,
    TaxonomyConfig,
    ValidatedClassification,
)
from web_backend.common import json_text, json_value, new_id
from web_backend.database import Database
from web_backend.result_state import result_delivery_state
from web_backend.security import utc_now

QUALITY_STATUSES = {"ready", "review_required", "unusable", "excluded"}
PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 200


class ClassificationResultNotFound(ValueError):
    pass


class ResultPublicationError(RuntimeError):
    pass


class ResultPublicationConflict(ResultPublicationError):
    pass


def _nullable_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _classification_quality(result: ValidatedClassification) -> str:
    if result.status == ProcessingStatus.MODEL_ERROR:
        return "unusable"
    if result.status.value in REVIEW_STATUSES:
        return "review_required"
    return "ready"


def _version_quality(qualities: list[str]) -> str:
    if qualities and all(value == "unusable" for value in qualities):
        return "unusable"
    if any(value != "ready" for value in qualities):
        return "review_required"
    return "ready"


class ClassificationResultService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def publish_v1(
        self,
        *,
        task_id: str,
        segment_id: str,
        dataset: ReturnDataset,
        results: dict[str, ValidatedClassification],
        taxonomy: TaxonomyConfig,
        segment_status: str,
        progress_total: int,
        model_calls: int,
        cache_hits: int,
        checkpoint_path: str,
        legacy_result_version: int,
        model_failures: int = 0,
    ) -> dict[str, Any]:
        prepared = self._prepare_publication(dataset, results, taxonomy)
        now = utc_now()
        conflict: str | None = None
        try:
            with self.database.transaction(immediate=True) as connection:
                task = connection.execute(
                    """
                    SELECT id, dataset_version_id, product_version_id,
                           owner_id, store, listing
                    FROM tasks WHERE id = ?
                    """,
                    (task_id,),
                ).fetchone()
                segment = connection.execute(
                    "SELECT * FROM task_segments WHERE id = ? AND task_id = ?",
                    (segment_id, task_id),
                ).fetchone()
                if task is None or segment is None:
                    raise ValueError("任务或 Listing 片段不存在")

                content_hash = self._content_hash(
                    str(task["dataset_version_id"]),
                    str(task["product_version_id"]),
                    prepared["units"],
                    prepared["records"],
                )
                existing = connection.execute(
                    """
                    SELECT v.* FROM classification_result_versions v
                    WHERE v.source_segment_id = ? AND v.version_no = 1
                    """,
                    (segment_id,),
                ).fetchone()
                if existing is not None:
                    if str(existing["content_hash"]) == content_hash:
                        return self._get_version_with_connection(
                            connection,
                            str(existing["id"]),
                        )
                    conflict = "Listing 片段 v1 已发布且内容哈希不同，拒绝覆盖"
                    connection.execute(
                        """
                        UPDATE task_segments
                        SET result_publish_error = ?, revision = revision + 1
                        WHERE id = ?
                        """,
                        (conflict, segment_id),
                    )
                    connection.execute(
                        """
                        INSERT INTO task_events(
                            task_id, event_type, stage, message,
                            data_json, created_at
                        ) VALUES (?, 'result_publish_conflict', '生成结果',
                                  ?, ?, ?)
                        """,
                        (
                            task_id,
                            conflict,
                            json_text(
                                {
                                    "segment_id": segment_id,
                                    "existing_content_hash": existing["content_hash"],
                                    "incoming_content_hash": content_hash,
                                }
                            ),
                            now,
                        ),
                    )
                else:
                    result_id = new_id("classification_result")
                    version_id = new_id("classification_version")
                    quality_status = _version_quality(
                        [str(value["quality_status"]) for value in prepared["units"]]
                    )
                    connection.execute(
                        """
                        INSERT INTO classification_results(
                            id, source_task_id, source_segment_id,
                            dataset_version_id, product_version_id,
                            store_site, listing, agent_key, agent_family,
                            logic_version, taxonomy_version,
                            model_policy_version, claims_version, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            result_id,
                            task_id,
                            segment_id,
                            task["dataset_version_id"],
                            task["product_version_id"],
                            prepared["store_site"] or task["store"],
                            prepared["listing"] or task["listing"],
                            segment["agent_key"],
                            segment["agent_family"],
                            segment["logic_version"],
                            segment["taxonomy_version"],
                            segment["model_policy_version"],
                            segment["claims_version"],
                            now,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO classification_result_versions(
                            id, result_id, source_segment_id, version_no,
                            content_hash, quality_status, publish_status,
                            unit_count, record_count, parent_version_id,
                            version_reason, created_by, created_at, published_at
                        ) VALUES (?, ?, ?, 1, ?, ?, 'publishing', ?, ?, NULL,
                                  '首次发布', ?, ?, NULL)
                        """,
                        (
                            version_id,
                            result_id,
                            segment_id,
                            content_hash,
                            quality_status,
                            len(prepared["units"]),
                            len(prepared["records"]),
                            task["owner_id"],
                            now,
                        ),
                    )
                    self._insert_units(
                        connection,
                        version_id,
                        prepared["units"],
                        prepared["labels"],
                    )
                    self._insert_records(
                        connection,
                        version_id,
                        str(task["dataset_version_id"]),
                        prepared["records"],
                    )
                    connection.execute(
                        """
                        UPDATE classification_result_versions
                        SET publish_status = 'published', published_at = ?
                        WHERE id = ?
                        """,
                        (now, version_id),
                    )
                    connection.execute(
                        """
                        UPDATE task_segments
                        SET status = ?, progress_current = ?, progress_total = ?,
                            model_calls = ?, cache_hits = ?, model_failures = ?,
                            error = NULL,
                            requested_action = NULL, result_json_path = ?,
                            result_version = ?, result_version_id = ?,
                            result_publish_status = 'published',
                            result_quality_status = ?, result_published_at = ?,
                            result_publish_error = NULL, completed_at = ?,
                            heartbeat_at = ?, revision = revision + 1
                        WHERE id = ? AND task_id = ?
                        """,
                        (
                            segment_status,
                            progress_total,
                            progress_total,
                            model_calls,
                            cache_hits,
                            model_failures,
                            checkpoint_path,
                            legacy_result_version,
                            version_id,
                            quality_status,
                            now,
                            now,
                            now,
                            segment_id,
                            task_id,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO task_events(
                            task_id, event_type, stage, message,
                            data_json, created_at
                        ) VALUES (?, 'segment_completed', '语义分析',
                                  'Listing 分类结果已发布', ?, ?)
                        """,
                        (
                            task_id,
                            json_text(
                                {
                                    "segment_id": segment_id,
                                    "status": segment_status,
                                    "result_version_id": version_id,
                                    "result_version": 1,
                                    "quality_status": quality_status,
                                }
                            ),
                            now,
                        ),
                    )
            if conflict is not None:
                raise ResultPublicationConflict(conflict)
        except ResultPublicationConflict:
            raise
        except Exception as exc:
            self.mark_publish_failed(task_id, segment_id, str(exc))
            raise ResultPublicationError(str(exc)) from exc
        version_id = self._published_version_id(segment_id)
        return self.get(version_id)

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

    def list(
        self,
        *,
        page: int = 1,
        page_size: int = PAGE_SIZE_DEFAULT,
        q: str | None = None,
        store_site: str | None = None,
        listing: str | None = None,
        quality_status: str | None = None,
    ) -> dict[str, Any]:
        page, page_size = self._validate_page(page, page_size)
        where = [
            "v.publish_status = 'published'",
            """
            v.version_no = (
                SELECT MAX(latest.version_no)
                FROM classification_result_versions latest
                WHERE latest.result_id = v.result_id
                  AND latest.publish_status = 'published'
            )
            """,
        ]
        params: list[Any] = []
        clean_query = (q or "").strip()
        if clean_query:
            pattern = self._contains_pattern(clean_query)
            where.append(
                """
                EXISTS (
                    SELECT 1 FROM classification_result_records search_record
                    WHERE search_record.result_version_id = v.id
                      AND (
                          search_record.product_name LIKE ? ESCAPE '\\'
                          OR search_record.listing LIKE ? ESCAPE '\\'
                          OR search_record.source_sku LIKE ? ESCAPE '\\'
                          OR search_record.product_sku LIKE ? ESCAPE '\\'
                      )
                )
                """
            )
            params.extend([pattern, pattern, pattern, pattern])
        if store_site:
            where.append("r.store_site = ?")
            params.append(store_site)
        if listing:
            where.append("r.listing = ?")
            params.append(listing)
        if quality_status:
            self._validate_quality_status(quality_status)
            where.append("v.quality_status = ?")
            params.append(quality_status)
        where_sql = " AND ".join(where)
        with self.database.connect() as connection:
            total = int(
                connection.execute(
                    f"""
                    SELECT COUNT(*) FROM classification_result_versions v
                    JOIN classification_results r ON r.id = v.result_id
                    WHERE {where_sql}
                    """,
                    tuple(params),
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                {self._version_select()}
                WHERE {where_sql}
                ORDER BY v.published_at DESC, v.id ASC
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "items": [self._serialize_version(dict(row)) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get(self, version_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            return self._get_version_with_connection(connection, version_id)

    def history(self, version_id: str) -> list[dict[str, Any]]:
        current = self.get(version_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                {self._version_select()}
                WHERE v.result_id = ? AND v.publish_status = 'published'
                ORDER BY v.version_no DESC
                """,
                (current["result_id"],),
            ).fetchall()
        return [self._serialize_version(dict(row)) for row in rows]

    def summary(self, version_id: str) -> dict[str, Any]:
        self.get(version_id)
        with self.database.connect() as connection:
            quality_rows = connection.execute(
                """
                SELECT quality_status, COUNT(*) AS unit_count,
                       COALESCE(SUM(record_count), 0) AS record_count
                FROM classification_units
                WHERE result_version_id = ?
                GROUP BY quality_status ORDER BY quality_status
                """,
                (version_id,),
            ).fetchall()
            status_rows = connection.execute(
                """
                SELECT processing_status, COUNT(*) AS unit_count,
                       COALESCE(SUM(record_count), 0) AS record_count
                FROM classification_units
                WHERE result_version_id = ?
                GROUP BY processing_status ORDER BY processing_status
                """,
                (version_id,),
            ).fetchall()
            problem_rows = connection.execute(
                """
                SELECT l.label_code, l.label_name, l.label_group,
                       COUNT(r.id) AS record_count,
                       COUNT(DISTINCT l.classification_key) AS unit_count
                FROM classification_unit_labels l
                JOIN classification_result_records r
                  ON r.result_version_id = l.result_version_id
                 AND r.classification_key = l.classification_key
                WHERE l.result_version_id = ? AND l.label_kind = 'problem'
                GROUP BY l.label_code, l.label_name, l.label_group
                ORDER BY record_count DESC, l.label_code ASC
                LIMIT 20
                """,
                (version_id,),
            ).fetchall()
        return {
            "version_id": version_id,
            "quality": [dict(row) for row in quality_rows],
            "processing_statuses": [dict(row) for row in status_rows],
            "top_problems": [dict(row) for row in problem_rows],
        }

    def records(
        self,
        version_id: str,
        *,
        page: int = 1,
        page_size: int = PAGE_SIZE_DEFAULT,
        **filters: str | None,
    ) -> dict[str, Any]:
        self.get(version_id)
        page, page_size = self._validate_page(page, page_size)
        where_sql, params = self._record_filters(version_id, filters)
        select_sql = self._records_select()
        with self.database.connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM classification_result_records r "
                    f"WHERE {where_sql}",
                    tuple(params),
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                {select_sql}
                WHERE {where_sql}
                ORDER BY r.source_row ASC, r.id ASC
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "items": [self._serialize_record(dict(row)) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def drilldown(
        self,
        version_id: str,
        group_by: str,
        *,
        page: int = 1,
        page_size: int = PAGE_SIZE_DEFAULT,
        **filters: str | None,
    ) -> dict[str, Any]:
        self.get(version_id)
        if group_by not in {"problem", "product_name", "product_sku"}:
            raise ValueError("group_by 仅支持 problem、product_name、product_sku")
        page, page_size = self._validate_page(page, page_size)
        where_sql, params = self._record_filters(version_id, filters)
        if group_by == "problem":
            join_sql = """
                JOIN classification_unit_labels l
                  ON l.result_version_id = r.result_version_id
                 AND l.classification_key = r.classification_key
                 AND l.label_kind = 'problem'
            """
            group_columns = "l.label_code, l.label_name, l.label_group"
            value_columns = """
                l.label_code AS value, l.label_name AS label_name,
                l.label_group AS label_group
            """
        else:
            join_sql = ""
            column = f"r.{group_by}"
            group_columns = column
            value_columns = f"{column} AS value"
        base_sql = f"""
            FROM classification_result_records r
            {join_sql}
            WHERE {where_sql}
            GROUP BY {group_columns}
        """
        with self.database.connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM (SELECT 1 {base_sql})",
                    tuple(params),
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT {value_columns}, COUNT(r.id) AS record_count,
                       COUNT(DISTINCT r.classification_key) AS unit_count
                {base_sql}
                ORDER BY record_count DESC, value ASC
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "group_by": group_by,
            "items": [dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def download(self, version_id: str) -> tuple[bytes, str]:
        version = self.get(version_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                {self._records_select()}
                WHERE r.result_version_id = ?
                ORDER BY r.source_row ASC, r.id ASC
                """,
                (version_id,),
            ).fetchall()
        output = []
        for row in rows:
            item = self._serialize_record(dict(row))
            output.append(
                {
                    "source_record_id": item["source_record_id"],
                    "source_row": item["source_row"],
                    "return_date": item["return_date"],
                    "order_id": item["order_id"],
                    "store_site": item["store_site"],
                    "listing": item["listing"],
                    "product_name": item["product_name"],
                    "source_sku": item["source_sku"],
                    "matched_msku": item["matched_msku"],
                    "product_sku": item["product_sku"],
                    "asin": item["asin"],
                    "category_a": item["category_a"],
                    "category_b": item["category_b"],
                    "reason": item["reason"],
                    "comment": item["comment"],
                    "product_match_status": item["product_match_status"],
                    "quality_status": item["quality_status"],
                    "processing_status": item["processing_status"],
                    "problem_labels": " | ".join(item["problem_labels"]),
                    "classification_json": json.dumps(
                        item["classification"],
                        ensure_ascii=False,
                    ),
                }
            )
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            pd.DataFrame(output).to_excel(
                writer,
                sheet_name="分类结果",
                index=False,
            )
        filename = (
            f"classification-{version['listing'] or version['result_id']}"
            f"-v{version['version']}.xlsx"
        )
        return buffer.getvalue(), filename

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
        for key in sorted(results):
            result = results[key]
            source = comments.loc[key]
            quality_status = _classification_quality(result)
            units.append(
                {
                    "classification_key": key,
                    "reason": _nullable_text(source.get("reason")),
                    "comment": _nullable_text(source.get("comment_normalized")),
                    "classification": result.model_dump(mode="json"),
                    "problem_labels": list(result.problem_label_codes),
                    "processing_status": result.status.value,
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
            result = results[str(row["classification_key"])]
            records.append(
                {
                    "classification_key": str(row["classification_key"]),
                    "source_row": int(row["source_row"]),
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
                    "quality_status": _classification_quality(result),
                }
            )
        scopes = {
            (value["store_site"], value["listing"])
            for value in records
        }
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
        hasher.update(
            f"{dataset_version_id}\x1f{product_version_id}\n".encode("utf-8")
        )
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
                processing_status, quality_status, record_count,
                model_name, prompt_version, taxonomy_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                source_record_id, source_row, return_date, order_id,
                store_site, listing, product_name, source_sku,
                matched_msku, product_sku, asin, fnsku, category_a,
                category_b, reason, comment, product_match_status,
                quality_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?)
            """,
            [
                (
                    new_id("classification_record"),
                    version_id,
                    value["classification_key"],
                    f"{dataset_version_id}:{value['source_row']}",
                    value["source_row"],
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
                WHERE source_segment_id = ? AND version_no = 1
                      AND publish_status = 'published'
                """,
                (segment_id,),
            ).fetchone()
        if row is None:
            raise ResultPublicationError("结果发布事务没有生成可用版本")
        return str(row["id"])

    @staticmethod
    def _version_select() -> str:
        return """
            SELECT v.id AS version_id, v.result_id, v.version_no AS version,
                   v.content_hash, v.quality_status, v.publish_status,
                   v.unit_count, v.record_count, v.created_at,
                   v.published_at, v.parent_version_id, v.version_reason,
                   v.created_by, creator.display_name AS created_by_name,
                   (
                       SELECT batch.id FROM review_batches batch
                       WHERE batch.published_version_id = v.id
                       ORDER BY batch.published_at DESC, batch.id DESC
                       LIMIT 1
                   ) AS source_review_batch_id,
                   (
                       SELECT parent.version_no
                       FROM classification_result_versions parent
                       WHERE parent.id = v.parent_version_id
                   ) AS parent_version_no,
                   COALESCE((
                       SELECT COUNT(DISTINCT revision.review_record_id)
                       FROM review_batches batch
                       JOIN review_records review
                         ON review.batch_id = batch.id
                       JOIN review_revisions revision
                         ON revision.review_record_id = review.id
                       WHERE batch.published_version_id = v.id
                         AND (
                             json_extract(
                                 revision.before_json, '$.semantic_units'
                             ) IS NOT json_extract(
                                 revision.after_json, '$.semantic_units'
                             )
                             OR json_extract(
                                 revision.before_json, '$.unknown_semantics'
                             ) IS NOT json_extract(
                                 revision.after_json, '$.unknown_semantics'
                             )
                             OR json_extract(
                                 revision.before_json, '$.problem_label_codes'
                             ) IS NOT json_extract(
                                 revision.after_json, '$.problem_label_codes'
                             )
                             OR json_extract(
                                 revision.before_json, '$.positive_label_codes'
                             ) IS NOT json_extract(
                                 revision.after_json, '$.positive_label_codes'
                             )
                             OR json_extract(
                                 revision.before_json, '$.primary_label_codes'
                             ) IS NOT json_extract(
                                 revision.after_json, '$.primary_label_codes'
                             )
                         )
                   ), 0) AS changed_unit_count,
                   r.source_task_id, r.source_segment_id,
                   r.dataset_version_id, r.product_version_id,
                   r.store_site, r.listing, r.agent_key, r.agent_family,
                   r.logic_version, r.taxonomy_version,
                   r.model_policy_version, r.claims_version,
                   rd.name AS dataset_name, dv.version AS dataset_version,
                   pd.name AS product_dataset_name,
                   pv.version AS product_version,
                   COALESCE((
                       SELECT json_group_array(product_name)
                       FROM (
                           SELECT DISTINCT records.product_name AS product_name
                           FROM classification_result_records records
                           WHERE records.result_version_id = v.id
                             AND records.product_name IS NOT NULL
                             AND TRIM(records.product_name) != ''
                           ORDER BY records.product_name COLLATE NOCASE,
                                    records.product_name
                       )
                   ), '[]') AS product_names_json
            FROM classification_result_versions v
            JOIN classification_results r ON r.id = v.result_id
            JOIN dataset_versions dv ON dv.id = r.dataset_version_id
            JOIN datasets rd ON rd.id = dv.dataset_id
            JOIN dataset_versions pv ON pv.id = r.product_version_id
            JOIN datasets pd ON pd.id = pv.dataset_id
            LEFT JOIN users creator ON creator.id = v.created_by
        """

    def _get_version_with_connection(
        self,
        connection: Any,
        version_id: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            f"{self._version_select()} WHERE v.id = ?",
            (version_id,),
        ).fetchone()
        if row is None:
            raise ClassificationResultNotFound("分类结果版本不存在")
        return self._serialize_version(dict(row))

    @staticmethod
    def _serialize_version(value: dict[str, Any]) -> dict[str, Any]:
        value["product_names"] = json_value(
            value.pop("product_names_json", None),
            [],
        )
        value["changed_unit_count"] = int(value.get("changed_unit_count") or 0)
        value["inherited_unit_count"] = (
            max(int(value.get("unit_count") or 0) - value["changed_unit_count"], 0)
            if value.get("parent_version_id")
            else 0
        )
        value.update(
            result_delivery_state(
                quality_status=value.get("quality_status"),
                publish_status=value.get("publish_status"),
                parent_version_id=value.get("parent_version_id"),
                source_review_batch_id=value.get("source_review_batch_id"),
            )
        )
        return value

    @staticmethod
    def _contains_pattern(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("%", "\\%")
        escaped = escaped.replace("_", "\\_")
        return f"%{escaped}%"

    @staticmethod
    def _records_select() -> str:
        return """
            SELECT r.*, u.processing_status, u.problem_labels_json,
                   u.classification_json
            FROM classification_result_records r
            JOIN classification_units u
              ON u.result_version_id = r.result_version_id
             AND u.classification_key = r.classification_key
        """

    @staticmethod
    def _serialize_record(value: dict[str, Any]) -> dict[str, Any]:
        value["problem_labels"] = json_value(
            value.pop("problem_labels_json", None),
            [],
        )
        value["classification"] = json_value(
            value.pop("classification_json", None),
            {},
        )
        return value

    def _record_filters(
        self,
        version_id: str,
        filters: dict[str, str | None],
    ) -> tuple[str, list[Any]]:
        where = ["r.result_version_id = ?"]
        params: list[Any] = [version_id]
        columns = {
            "order_id": "order_id",
            "listing": "listing",
            "source_sku": "source_sku",
            "matched_msku": "matched_msku",
            "product_sku": "product_sku",
            "asin": "asin",
            "product_name": "product_name",
        }
        for name, column in columns.items():
            value = filters.get(name)
            if value:
                where.append(f"r.{column} = ?")
                params.append(value)
        quality_status = filters.get("quality_status")
        if quality_status:
            self._validate_quality_status(quality_status)
            where.append("r.quality_status = ?")
            params.append(quality_status)
        problem = filters.get("problem")
        if problem:
            where.append(
                """
                EXISTS (
                    SELECT 1 FROM classification_unit_labels f
                    WHERE f.result_version_id = r.result_version_id
                      AND f.classification_key = r.classification_key
                      AND f.label_kind = 'problem' AND f.label_code = ?
                )
                """
            )
            params.append(problem)
        return " AND ".join(where), params

    @staticmethod
    def _validate_page(page: int, page_size: int) -> tuple[int, int]:
        if page < 1:
            raise ValueError("page 必须大于等于 1")
        if not 1 <= page_size <= PAGE_SIZE_MAX:
            raise ValueError(f"page_size 必须在 1 到 {PAGE_SIZE_MAX} 之间")
        return page, page_size

    @staticmethod
    def _validate_quality_status(value: str) -> None:
        if value not in QUALITY_STATUSES:
            raise ValueError("quality_status 不合法")
