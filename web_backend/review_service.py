from __future__ import annotations

import json
import threading
from collections import Counter
from pathlib import Path
from typing import Any

from return_semantics.capabilities import load_capability_registry
from return_semantics.data import load_return_dataset
from return_semantics.exporter import export_results
from return_semantics.schemas import ValidatedClassification
from web_backend.classification_result_service import ClassificationResultService
from web_backend.common import add_audit, json_text, json_value, new_id
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.settings import PROJECT_ROOT

_TASK_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()

_BATCH_SUMMARY_SELECT = """
    SELECT b.*, base.version_no AS version_no,
           base.version_no AS base_version_no,
           base.quality_status AS quality_status,
           base.quality_status AS base_quality_status,
           base.unit_count AS unit_count,
           base.unit_count AS base_unit_count,
           base.record_count AS base_record_count,
           result.store_site, result.listing,
           creator.display_name AS creator_name,
           COUNT(rr.id) AS record_count,
           COALESCE(SUM(
               CASE WHEN rr.workflow_status = 'resolved' THEN 1 ELSE 0 END
           ), 0) AS resolved_count,
           COALESCE(SUM(
               CASE WHEN rr.workflow_status = 'excluded' THEN 1 ELSE 0 END
           ), 0) AS excluded_count,
           b.published_version_id AS derived_result_version_id,
           derived.version_no AS derived_version_no,
           derived.quality_status AS derived_quality_status,
           derived.published_at AS derived_published_at
    FROM review_batches b
    JOIN classification_result_versions base
      ON base.id = b.base_result_version_id
    JOIN classification_results result ON result.id = b.result_id
    JOIN users creator ON creator.id = b.created_by
    LEFT JOIN review_records rr ON rr.batch_id = b.id
    LEFT JOIN classification_result_versions derived
      ON derived.id = b.published_version_id
"""


def _task_lock(task_id: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _TASK_LOCKS.setdefault(task_id, threading.Lock())


class RevisionConflict(ValueError):
    pass


class ReviewBatchConflict(ValueError):
    pass


class ReviewService:
    def __init__(
        self,
        database: Database,
        result_service: ClassificationResultService | None = None,
    ) -> None:
        self.database = database
        self.result_service = result_service or ClassificationResultService(database)
        self.capability_registry = load_capability_registry(
            PROJECT_ROOT / "config" / "category_capabilities.json"
        )

    def list(
        self,
        workflow_status: str | None = None,
        task_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT r.*, t.title AS task_title, t.owner_id,
                   owner.display_name AS owner_name,
                   editor.display_name AS updated_by_name
            FROM review_records r
            JOIN tasks t ON t.id = r.task_id
            JOIN users owner ON owner.id = t.owner_id
            LEFT JOIN users editor ON editor.id = r.updated_by
            WHERE r.batch_id IS NULL
        """
        params: list[object] = []
        if workflow_status:
            query += " AND r.workflow_status = ?"
            params.append(workflow_status)
        if task_id:
            query += " AND r.task_id = ?"
            params.append(task_id)
        query += " ORDER BY r.updated_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._serialize(dict(row)) for row in rows]

    def get(self, review_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT r.*, t.title AS task_title,
                       owner.display_name AS owner_name,
                       editor.display_name AS updated_by_name
                FROM review_records r
                JOIN tasks t ON t.id = r.task_id
                JOIN users owner ON owner.id = t.owner_id
                LEFT JOIN users editor ON editor.id = r.updated_by
                WHERE r.id = ?
                """,
                (review_id,),
            ).fetchone()
            if row is None:
                return None
            revisions = connection.execute(
                """
                SELECT rr.*, u.display_name AS actor_name
                FROM review_revisions rr
                JOIN users u ON u.id = rr.actor_id
                WHERE rr.review_record_id = ?
                ORDER BY rr.revision DESC
                """,
                (review_id,),
            ).fetchall()
        item = self._serialize(dict(row))
        item["revisions"] = [
            self._serialize_revision(dict(value)) for value in revisions
        ]
        return item

    def create_batch(
        self,
        base_result_version_id: str,
        actor_id: str,
        reason: str,
    ) -> dict[str, Any]:
        clean_reason = reason.strip()
        if not clean_reason:
            raise ValueError("请填写创建复核批次原因")
        now = utc_now()
        batch_id = new_id("review_batch")
        with self.database.transaction(immediate=True) as connection:
            base = connection.execute(
                """
                SELECT v.*, r.source_task_id
                FROM classification_result_versions v
                JOIN classification_results r ON r.id = v.result_id
                WHERE v.id = ? AND v.publish_status = 'published'
                """,
                (base_result_version_id,),
            ).fetchone()
            if base is None:
                raise ValueError("基准分类结果版本不存在或尚未发布")
            existing_draft = connection.execute(
                """
                SELECT id FROM review_batches
                WHERE base_result_version_id = ? AND status = 'draft'
                LIMIT 1
                """,
                (base_result_version_id,),
            ).fetchone()
            if existing_draft is not None:
                raise ReviewBatchConflict("该分类结果版本已有未发布的复核批次")
            units = connection.execute(
                """
                SELECT classification_key, comment, classification_json
                FROM classification_units
                WHERE result_version_id = ? AND quality_status != 'ready'
                ORDER BY classification_key
                """,
                (base_result_version_id,),
            ).fetchall()
            if not units:
                raise ValueError("该结果版本没有需要复核的分类单元")
            connection.execute(
                """
                INSERT INTO review_batches(
                    id, base_result_version_id, result_id, status,
                    revision, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, 'draft', 1, ?, ?, ?)
                """,
                (
                    batch_id,
                    base_result_version_id,
                    base["result_id"],
                    actor_id,
                    now,
                    now,
                ),
            )
            connection.executemany(
                """
                INSERT INTO review_records(
                    id, task_id, batch_id, base_result_version_id,
                    classification_key, comment, workflow_status,
                    classification_json, revision, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, 1, ?)
                """,
                [
                    (
                        new_id("review"),
                        base["source_task_id"],
                        batch_id,
                        base_result_version_id,
                        unit["classification_key"],
                        str(unit["comment"] or ""),
                        unit["classification_json"],
                        now,
                    )
                    for unit in units
                ],
            )
            event_data = {
                "batch_id": batch_id,
                "base_result_version_id": base_result_version_id,
                "record_count": len(units),
                "reason": clean_reason,
            }
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'review_batch_created', '人工复核',
                          '已创建分类结果复核批次', ?, ?, ?)
                """,
                (
                    base["source_task_id"],
                    actor_id,
                    json_text(event_data),
                    now,
                ),
            )
            self._insert_audit(
                connection,
                batch_id,
                "create",
                actor_id,
                {},
                event_data,
                now,
            )
        return self.get_batch(batch_id)

    def list_batches(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        status: str | None = None,
        base_result_version_id: str | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        page, page_size = ClassificationResultService._validate_page(
            page,
            page_size,
        )
        where: list[str] = []
        params: list[Any] = []
        if status:
            if status not in {"draft", "published"}:
                raise ValueError("status 仅支持 draft 或 published")
            where.append("b.status = ?")
            params.append(status)
        if base_result_version_id:
            where.append("b.base_result_version_id = ?")
            params.append(base_result_version_id)
        clean_query = (q or "").strip()
        if clean_query:
            pattern = ClassificationResultService._contains_pattern(clean_query)
            where.append(
                """
                (
                    result.listing LIKE ? ESCAPE '\\'
                    OR b.id LIKE ? ESCAPE '\\'
                    OR creator.display_name LIKE ? ESCAPE '\\'
                    OR b.created_by LIKE ? ESCAPE '\\'
                )
                """
            )
            params.extend([pattern, pattern, pattern, pattern])
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        joins = """
            FROM review_batches b
            JOIN classification_result_versions base
              ON base.id = b.base_result_version_id
            JOIN classification_results result ON result.id = b.result_id
            JOIN users creator ON creator.id = b.created_by
        """
        with self.database.connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) {joins} {where_sql}",
                    tuple(params),
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                {_BATCH_SUMMARY_SELECT}
                {where_sql}
                GROUP BY b.id
                ORDER BY b.updated_at DESC, b.id DESC
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "items": [self._serialize_batch(dict(row)) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_batch(self, batch_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                f"""
                {_BATCH_SUMMARY_SELECT}
                WHERE b.id = ?
                GROUP BY b.id
                """,
                (batch_id,),
            ).fetchone()
        if row is None:
            raise ValueError("复核批次不存在")
        return self._serialize_batch(dict(row))

    def batch_records(
        self,
        batch_id: str,
        *,
        page: int = 1,
        page_size: int = 50,
        workflow_status: str | None = None,
        q: str | None = None,
        listing: str | None = None,
        product_name: str | None = None,
        product_sku: str | None = None,
        order_id: str | None = None,
    ) -> dict[str, Any]:
        self.get_batch(batch_id)
        page, page_size = ClassificationResultService._validate_page(
            page,
            page_size,
        )
        where = ["r.batch_id = ?"]
        params: list[Any] = [batch_id]
        if workflow_status:
            where.append("r.workflow_status = ?")
            params.append(workflow_status)
        record_filters = {
            "listing": listing,
            "product_name": product_name,
            "product_sku": product_sku,
            "order_id": order_id,
        }
        business_where: list[str] = []
        for column, value in record_filters.items():
            if value:
                business_where.append(f"filtered.{column} = ?")
                params.append(value)
        if business_where:
            where.append(
                f"""
                EXISTS (
                    SELECT 1 FROM classification_result_records filtered
                    WHERE filtered.result_version_id = b.base_result_version_id
                      AND filtered.classification_key = r.classification_key
                      AND {" AND ".join(business_where)}
                )
                """
            )
        clean_query = (q or "").strip()
        if clean_query:
            pattern = ClassificationResultService._contains_pattern(clean_query)
            where.append(
                """
                (
                    r.comment LIKE ? ESCAPE '\\'
                    OR r.classification_key LIKE ? ESCAPE '\\'
                    OR EXISTS (
                        SELECT 1 FROM classification_result_records searched
                        WHERE searched.result_version_id = b.base_result_version_id
                          AND searched.classification_key = r.classification_key
                          AND (
                              searched.order_id LIKE ? ESCAPE '\\'
                              OR searched.product_name LIKE ? ESCAPE '\\'
                              OR searched.listing LIKE ? ESCAPE '\\'
                              OR searched.source_sku LIKE ? ESCAPE '\\'
                              OR searched.matched_msku LIKE ? ESCAPE '\\'
                              OR searched.product_sku LIKE ? ESCAPE '\\'
                          )
                    )
                )
                """
            )
            params.extend([pattern] * 8)
        where_sql = " AND ".join(where)
        with self.database.connect() as connection:
            total = int(
                connection.execute(
                    f"""
                    SELECT COUNT(*) FROM review_records r
                    JOIN review_batches b ON b.id = r.batch_id
                    WHERE {where_sql}
                    """,
                    tuple(params),
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT r.*, editor.display_name AS updated_by_name,
                       COUNT(business.id) AS record_count,
                       COALESCE(json_group_array(DISTINCT business.order_id)
                           FILTER (WHERE NULLIF(TRIM(business.order_id), '')
                           IS NOT NULL), '[]') AS order_ids_json,
                       COALESCE(json_group_array(DISTINCT business.product_name)
                           FILTER (WHERE NULLIF(TRIM(business.product_name), '')
                           IS NOT NULL), '[]') AS product_names_json,
                       COALESCE(json_group_array(DISTINCT business.listing)
                           FILTER (WHERE NULLIF(TRIM(business.listing), '')
                           IS NOT NULL), '[]') AS listings_json,
                       COALESCE(json_group_array(DISTINCT business.source_sku)
                           FILTER (WHERE NULLIF(TRIM(business.source_sku), '')
                           IS NOT NULL), '[]') AS source_skus_json,
                       COALESCE(json_group_array(DISTINCT business.matched_msku)
                           FILTER (WHERE NULLIF(TRIM(business.matched_msku), '')
                           IS NOT NULL), '[]') AS matched_mskus_json,
                       COALESCE(json_group_array(DISTINCT business.product_sku)
                           FILTER (WHERE NULLIF(TRIM(business.product_sku), '')
                           IS NOT NULL), '[]') AS product_skus_json
                FROM review_records r
                JOIN review_batches b ON b.id = r.batch_id
                LEFT JOIN users editor ON editor.id = r.updated_by
                LEFT JOIN classification_result_records business
                  ON business.result_version_id = b.base_result_version_id
                 AND business.classification_key = r.classification_key
                WHERE {where_sql}
                GROUP BY r.id
                ORDER BY r.classification_key, r.id
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "items": [self._serialize_batch_record(dict(row)) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def update_batch_record(
        self,
        batch_id: str,
        review_id: str,
        expected_revision: int,
        actor_id: str,
        label_code: str | None,
        note: str,
        action: str | None = None,
    ) -> dict[str, Any]:
        clean_note = note.strip()
        if not clean_note:
            raise ValueError("请填写修改原因")
        resolved_action = action or ("modify" if label_code else "confirm")
        now = utc_now()
        try:
            with self.database.transaction(immediate=True) as connection:
                batch = connection.execute(
                    "SELECT * FROM review_batches WHERE id = ?",
                    (batch_id,),
                ).fetchone()
                if batch is None:
                    raise ValueError("复核批次不存在")
                if batch["status"] != "draft":
                    raise ReviewBatchConflict("已发布的复核批次不能修改")
                row = connection.execute(
                    """
                    SELECT * FROM review_records
                    WHERE id = ? AND batch_id = ?
                    """,
                    (review_id, batch_id),
                ).fetchone()
                if row is None:
                    raise ValueError("批次复核记录不存在")
                before, after = self._update_batch_record_row(
                    connection,
                    row,
                    expected_revision=expected_revision,
                    actor_id=actor_id,
                    action=resolved_action,
                    label_code=label_code,
                    note=clean_note,
                    now=now,
                )
                connection.execute(
                    """
                    UPDATE review_batches
                    SET revision = revision + 1, updated_at = ? WHERE id = ?
                    """,
                    (now, batch_id),
                )
                event_data = {
                    "batch_id": batch_id,
                    "review_id": review_id,
                    "classification_key": row["classification_key"],
                    "action": resolved_action,
                    "reason": clean_note,
                }
                connection.execute(
                    """
                    INSERT INTO task_events(
                        task_id, event_type, stage, message, actor_id,
                        data_json, created_at
                    ) VALUES (?, 'review_batch_record_updated', '人工复核',
                              '复核批次草稿已修改', ?, ?, ?)
                    """,
                    (row["task_id"], actor_id, json_text(event_data), now),
                )
                self._insert_audit(
                    connection,
                    batch_id,
                    "update_record",
                    actor_id,
                    {"review_id": review_id, "classification": before},
                    {
                        "review_id": review_id,
                        "classification": after,
                        "action": resolved_action,
                        "reason": clean_note,
                    },
                    now,
                )
        except (ReviewBatchConflict, RevisionConflict) as exc:
            self._record_batch_conflict(batch_id, actor_id, str(exc))
            raise
        return self.get(review_id) or {}

    def update_batch_records(
        self,
        batch_id: str,
        records: list[dict[str, Any]],
        actor_id: str,
        action: str,
        label_code: str | None,
        note: str,
    ) -> dict[str, Any]:
        clean_note = note.strip()
        if not clean_note:
            raise ValueError("请填写处理原因")
        if not records:
            raise ValueError("请选择至少一条复核记录")
        review_ids = [str(record["id"]) for record in records]
        if len(review_ids) != len(set(review_ids)):
            raise ValueError("批量复核记录不能重复")
        now = utc_now()
        try:
            with self.database.transaction(immediate=True) as connection:
                batch = connection.execute(
                    "SELECT * FROM review_batches WHERE id = ?",
                    (batch_id,),
                ).fetchone()
                if batch is None:
                    raise ValueError("复核批次不存在")
                if batch["status"] != "draft":
                    raise ReviewBatchConflict("已发布的复核批次不能修改")
                placeholders = ",".join("?" for _ in review_ids)
                rows = connection.execute(
                    f"""
                    SELECT * FROM review_records
                    WHERE batch_id = ? AND id IN ({placeholders})
                    """,
                    (batch_id, *review_ids),
                ).fetchall()
                rows_by_id = {str(row["id"]): row for row in rows}
                if len(rows_by_id) != len(review_ids):
                    raise ValueError("部分复核记录不存在")
                expected_by_id = {
                    str(record["id"]): int(record["expected_revision"])
                    for record in records
                }
                changes = []
                for review_id in review_ids:
                    row = rows_by_id[review_id]
                    before, after = self._update_batch_record_row(
                        connection,
                        row,
                        expected_revision=expected_by_id[review_id],
                        actor_id=actor_id,
                        action=action,
                        label_code=label_code,
                        note=clean_note,
                        now=now,
                    )
                    changes.append(
                        {
                            "review_id": review_id,
                            "classification_key": row["classification_key"],
                            "before": before,
                            "after": after,
                        }
                    )
                connection.execute(
                    """
                    UPDATE review_batches
                    SET revision = revision + 1, updated_at = ? WHERE id = ?
                    """,
                    (now, batch_id),
                )
                event_data = {
                    "batch_id": batch_id,
                    "review_ids": review_ids,
                    "action": action,
                    "updated_count": len(changes),
                    "reason": clean_note,
                }
                connection.execute(
                    """
                    INSERT INTO task_events(
                        task_id, event_type, stage, message, actor_id,
                        data_json, created_at
                    ) VALUES (?, 'review_batch_records_updated', '人工复核',
                              '复核批次已批量处理', ?, ?, ?)
                    """,
                    (
                        rows[0]["task_id"],
                        actor_id,
                        json_text(event_data),
                        now,
                    ),
                )
                self._insert_audit(
                    connection,
                    batch_id,
                    "bulk_update_records",
                    actor_id,
                    {"review_ids": review_ids},
                    {
                        "review_ids": review_ids,
                        "action": action,
                        "updated_count": len(changes),
                        "reason": clean_note,
                    },
                    now,
                )
        except (ReviewBatchConflict, RevisionConflict) as exc:
            self._record_batch_conflict(batch_id, actor_id, str(exc))
            raise
        return {"updated_count": len(review_ids), "batch": self.get_batch(batch_id)}

    def _update_batch_record_row(
        self,
        connection: Any,
        row: Any,
        *,
        expected_revision: int,
        actor_id: str,
        action: str,
        label_code: str | None,
        note: str,
        now: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if action not in {"confirm", "modify", "exclude"}:
            raise ValueError("复核处理动作不合法")
        if action == "modify" and not str(label_code or "").strip():
            raise ValueError("修改分类时请选择目标标签")
        if int(row["revision"]) != expected_revision:
            raise RevisionConflict("记录已被其他用户修改，请刷新后重试")
        if row["workflow_status"] != "pending":
            raise ReviewBatchConflict("只能处理待处理的复核记录")
        before = json_value(str(row["classification_json"]), {})
        after = (
            before
            if action == "exclude"
            else self._apply_resolution(
                before,
                str(row["comment"]),
                label_code if action == "modify" else None,
            )
        )
        next_revision = expected_revision + 1
        workflow_status = "excluded" if action == "exclude" else "resolved"
        connection.execute(
            """
            UPDATE review_records
            SET workflow_status = ?, classification_json = ?,
                revision = ?, updated_by = ?, updated_at = ?
            WHERE id = ? AND batch_id = ? AND revision = ?
            """,
            (
                workflow_status,
                json_text(after),
                next_revision,
                actor_id,
                now,
                row["id"],
                row["batch_id"],
                expected_revision,
            ),
        )
        connection.execute(
            """
            INSERT INTO review_revisions(
                id, review_record_id, revision, before_json, after_json,
                note, actor_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("revision"),
                row["id"],
                next_revision,
                json_text(before),
                json_text(after),
                note,
                actor_id,
                now,
            ),
        )
        return before, after

    def publish_batch(
        self,
        batch_id: str,
        expected_revision: int,
        actor_id: str,
        reason: str,
    ) -> dict[str, Any]:
        clean_reason = reason.strip()
        if not clean_reason:
            raise ValueError("请填写发布原因")
        taxonomy = self.capability_registry.combined_taxonomy()
        label_map = {label.code: label for label in taxonomy.labels}
        now = utc_now()
        try:
            with self.database.transaction(immediate=True) as connection:
                batch = connection.execute(
                    """
                    SELECT b.*, v.source_segment_id, v.content_hash AS base_hash,
                           v.publish_status AS base_publish_status,
                           r.source_task_id, r.dataset_version_id,
                           r.product_version_id
                    FROM review_batches b
                    JOIN classification_result_versions v
                      ON v.id = b.base_result_version_id
                    JOIN classification_results r ON r.id = b.result_id
                    WHERE b.id = ?
                    """,
                    (batch_id,),
                ).fetchone()
                if batch is None:
                    raise ValueError("复核批次不存在")
                if int(batch["revision"]) != expected_revision:
                    raise RevisionConflict("批次已被其他用户修改，请刷新后重试")
                if batch["status"] == "published":
                    raise ReviewBatchConflict("复核批次已经发布，不能重复提交")
                if batch["base_publish_status"] != "published":
                    raise ReviewBatchConflict("基准分类结果版本不可用")
                review_count = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM review_records WHERE batch_id = ?",
                        (batch_id,),
                    ).fetchone()[0]
                )
                if review_count == 0:
                    raise ReviewBatchConflict("复核批次没有可处理的复核记录")
                pending_count = int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM review_records
                        WHERE batch_id = ?
                          AND workflow_status NOT IN ('resolved', 'excluded')
                        """,
                        (batch_id,),
                    ).fetchone()[0]
                )
                if pending_count:
                    raise ReviewBatchConflict(
                        f"复核批次仍有 {pending_count} 条记录未完成"
                    )
                revisions = {
                    str(row["classification_key"]): json_value(
                        row["classification_json"],
                        {},
                    )
                    for row in connection.execute(
                        """
                        SELECT classification_key, classification_json
                        FROM review_records
                        WHERE batch_id = ? AND workflow_status = 'resolved'
                        """,
                        (batch_id,),
                    ).fetchall()
                }
                excluded_keys = {
                    str(row["classification_key"])
                    for row in connection.execute(
                        """
                        SELECT classification_key FROM review_records
                        WHERE batch_id = ? AND workflow_status = 'excluded'
                        """,
                        (batch_id,),
                    ).fetchall()
                }
                base_units = connection.execute(
                    """
                    SELECT * FROM classification_units
                    WHERE result_version_id = ? ORDER BY classification_key
                    """,
                    (batch["base_result_version_id"],),
                ).fetchall()
                base_labels: dict[str, list[dict[str, Any]]] = {}
                for label_row in connection.execute(
                    """
                    SELECT classification_key, label_kind, label_code,
                           label_name, label_group
                    FROM classification_unit_labels
                    WHERE result_version_id = ?
                    ORDER BY classification_key, label_kind, label_code
                    """,
                    (batch["base_result_version_id"],),
                ).fetchall():
                    base_labels.setdefault(
                        str(label_row["classification_key"]),
                        [],
                    ).append(dict(label_row))
                units: list[dict[str, Any]] = []
                labels: list[dict[str, Any]] = []
                unit_quality: dict[str, str] = {}
                for row in base_units:
                    key = str(row["classification_key"])
                    classification = revisions.get(
                        key,
                        json_value(row["classification_json"], {}),
                    )
                    validated = ValidatedClassification.model_validate(classification)
                    quality_status = (
                        "excluded"
                        if key in excluded_keys
                        else "ready"
                        if key in revisions
                        else str(row["quality_status"])
                    )
                    unit_quality[key] = quality_status
                    units.append(
                        {
                            "classification_key": key,
                            "reason": row["reason"],
                            "comment": row["comment"],
                            "classification": validated.model_dump(mode="json"),
                            "problem_labels": list(validated.problem_label_codes),
                            "processing_status": validated.status.value,
                            "quality_status": quality_status,
                            "record_count": int(row["record_count"]),
                            "model_name": validated.model_name,
                            "prompt_version": validated.prompt_version,
                            "taxonomy_version": validated.taxonomy_version,
                        }
                    )
                    if key in excluded_keys:
                        continue
                    if key not in revisions:
                        labels.extend(base_labels.get(key, []))
                    else:
                        for kind, codes in (
                            ("problem", validated.problem_label_codes),
                            ("positive", validated.positive_label_codes),
                            ("primary", validated.primary_label_codes),
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
                base_records = connection.execute(
                    """
                    SELECT * FROM classification_result_records
                    WHERE result_version_id = ? ORDER BY source_row, id
                    """,
                    (batch["base_result_version_id"],),
                ).fetchall()
                records = [
                    {
                        "classification_key": str(row["classification_key"]),
                        "source_row": int(row["source_row"]),
                        "return_date": row["return_date"],
                        "order_id": row["order_id"],
                        "store_site": row["store_site"],
                        "listing": row["listing"],
                        "product_name": row["product_name"],
                        "source_sku": row["source_sku"],
                        "matched_msku": row["matched_msku"],
                        "product_sku": row["product_sku"],
                        "asin": row["asin"],
                        "fnsku": row["fnsku"],
                        "category_a": row["category_a"],
                        "category_b": row["category_b"],
                        "reason": row["reason"],
                        "comment": row["comment"],
                        "product_match_status": row["product_match_status"],
                        "quality_status": unit_quality[str(row["classification_key"])],
                    }
                    for row in base_records
                ]
                next_version = int(
                    connection.execute(
                        """
                        SELECT COALESCE(MAX(version_no), 0) + 1
                        FROM classification_result_versions WHERE result_id = ?
                        """,
                        (batch["result_id"],),
                    ).fetchone()[0]
                )
                version_id = new_id("classification_version")
                qualities = [str(unit["quality_status"]) for unit in units]
                quality_status = self._version_quality(qualities)
                content_hash = self.result_service._content_hash(
                    str(batch["dataset_version_id"]),
                    str(batch["product_version_id"]),
                    units,
                    records,
                )
                connection.execute(
                    """
                    INSERT INTO classification_result_versions(
                        id, result_id, source_segment_id, version_no,
                        content_hash, quality_status, publish_status,
                        unit_count, record_count, parent_version_id,
                        version_reason, created_by, created_at, published_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'publishing', ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        version_id,
                        batch["result_id"],
                        batch["source_segment_id"],
                        next_version,
                        content_hash,
                        quality_status,
                        len(units),
                        len(records),
                        batch["base_result_version_id"],
                        clean_reason,
                        actor_id,
                        now,
                    ),
                )
                self.result_service._insert_units(
                    connection,
                    version_id,
                    units,
                    labels,
                )
                self.result_service._insert_records(
                    connection,
                    version_id,
                    str(batch["dataset_version_id"]),
                    records,
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
                    UPDATE review_batches
                    SET status = 'published', revision = revision + 1,
                        updated_at = ?, published_version_id = ?, published_at = ?
                    WHERE id = ? AND revision = ? AND status = 'draft'
                    """,
                    (now, version_id, now, batch_id, expected_revision),
                )
                event_data = {
                    "batch_id": batch_id,
                    "base_result_version_id": batch["base_result_version_id"],
                    "result_version_id": version_id,
                    "version": next_version,
                    "reason": clean_reason,
                }
                connection.execute(
                    """
                    INSERT INTO task_events(
                        task_id, event_type, stage, message, actor_id,
                        data_json, created_at
                    ) VALUES (?, 'review_batch_published', '人工复核',
                              '复核批次已发布为新的分类结果版本', ?, ?, ?)
                    """,
                    (
                        batch["source_task_id"],
                        actor_id,
                        json_text(event_data),
                        now,
                    ),
                )
                self._insert_audit(
                    connection,
                    batch_id,
                    "publish",
                    actor_id,
                    {
                        "status": "draft",
                        "base_result_version_id": batch["base_result_version_id"],
                    },
                    {
                        "status": "published",
                        "result_version_id": version_id,
                        "reason": clean_reason,
                    },
                    now,
                )
        except (RevisionConflict, ReviewBatchConflict) as exc:
            self._record_batch_conflict(batch_id, actor_id, str(exc))
            raise
        return self.result_service.get(version_id)

    def resolve(
        self,
        review_id: str,
        expected_revision: int,
        actor_id: str,
        label_code: str | None,
        note: str,
    ) -> dict[str, Any]:
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT * FROM review_records WHERE id = ?",
                (review_id,),
            ).fetchone()
            if row is None:
                raise ValueError("复核记录不存在")
            if row["batch_id"] is not None:
                raise ValueError("新复核记录请使用批次草稿接口修改")
            if int(row["revision"]) != expected_revision:
                raise RevisionConflict("记录已被其他用户修改，请刷新后重试")
            before = json_value(str(row["classification_json"]), {})
            after = self._apply_resolution(before, str(row["comment"]), label_code)
            next_revision = expected_revision + 1
            revision_id = new_id("revision")
            now = utc_now()
            connection.execute(
                """
                UPDATE review_records
                SET workflow_status = 'resolved', classification_json = ?,
                    revision = ?, updated_by = ?, updated_at = ?
                WHERE id = ? AND revision = ?
                """,
                (
                    json_text(after),
                    next_revision,
                    actor_id,
                    now,
                    review_id,
                    expected_revision,
                ),
            )
            connection.execute(
                """
                INSERT INTO review_revisions(
                    id, review_record_id, revision, before_json, after_json,
                    note, actor_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    review_id,
                    next_revision,
                    json_text(before),
                    json_text(after),
                    note.strip(),
                    actor_id,
                    now,
                ),
            )
            task_id = str(row["task_id"])
            previous_state = {
                "workflow_status": str(row["workflow_status"]),
                "updated_by": row["updated_by"],
                "updated_at": str(row["updated_at"]),
            }
        try:
            self._rebuild_result(task_id, actor_id)
        except Exception:
            with self.database.transaction(immediate=True) as connection:
                connection.execute(
                    """
                    UPDATE review_records
                    SET workflow_status = ?, classification_json = ?,
                        revision = ?, updated_by = ?, updated_at = ?
                    WHERE id = ? AND revision = ?
                    """,
                    (
                        previous_state["workflow_status"],
                        json_text(before),
                        expected_revision,
                        previous_state["updated_by"],
                        previous_state["updated_at"],
                        review_id,
                        next_revision,
                    ),
                )
                connection.execute(
                    "DELETE FROM review_revisions WHERE id = ?",
                    (revision_id,),
                )
            raise
        add_audit(
            self.database,
            "review",
            review_id,
            "resolve",
            actor_id,
            before=before,
            after=after,
        )
        return self.get(review_id) or {}

    def _apply_resolution(
        self,
        classification: dict[str, Any],
        comment: str,
        label_code: str | None,
    ) -> dict[str, Any]:
        taxonomy = self.capability_registry.combined_taxonomy()
        label_codes = {label.code for label in taxonomy.labels}
        selected = (label_code or "").strip()
        updated = dict(classification)
        if selected:
            if selected not in label_codes:
                raise ValueError("选择的语义标签不存在")
            units = [dict(item) for item in updated.get("semantic_units", [])]
            if units:
                units[0]["label_code"] = selected
            else:
                units = [
                    {
                        "subject": "PRODUCT",
                        "label_code": selected,
                        "opinion": comment,
                        "sentiment": "NEGATIVE",
                        "assertion": "AFFIRMED",
                        "part": "UNSPECIFIED",
                        "evidence": comment,
                        "implicit": False,
                        "claim_relation": "NONE",
                        "claim_id": None,
                    }
                ]
            updated["semantic_units"] = units
            updated["unknown_semantics"] = []
            updated["problem_label_codes"] = [selected]
            updated["positive_label_codes"] = []
            updated["primary_label_codes"] = [selected]
        if not updated.get("semantic_units") and updated.get("unknown_semantics"):
            raise ValueError("未知语义必须选择一个标签后才能完成复核")
        updated["status"] = "MANUAL_RESOLVED"
        updated["review_reasons"] = []
        ValidatedClassification.model_validate(updated)
        return updated

    def _rebuild_result(self, task_id: str, actor_id: str) -> None:
        with _task_lock(task_id):
            with self.database.connect() as connection:
                task = connection.execute(
                    """
                    SELECT t.*, rv.file_path AS return_file_path,
                           pv.file_path AS product_file_path
                    FROM tasks t
                    JOIN dataset_versions rv ON rv.id = t.dataset_version_id
                    JOIN dataset_versions pv ON pv.id = t.product_version_id
                    WHERE t.id = ?
                    """,
                    (task_id,),
                ).fetchone()
                reviews = connection.execute(
                    """
                    SELECT classification_key, classification_json
                    FROM review_records WHERE task_id = ? AND batch_id IS NULL
                    """,
                    (task_id,),
                ).fetchall()
                resolved = connection.execute(
                    """
                    SELECT COUNT(*) AS count FROM review_records
                    WHERE task_id = ? AND batch_id IS NULL
                      AND workflow_status = 'resolved'
                    """,
                    (task_id,),
                ).fetchone()
            if task is None or not task["results_json_path"]:
                raise ValueError("任务结果尚未生成")
            results_path = Path(str(task["results_json_path"]))
            payload = json.loads(results_path.read_text(encoding="utf-8"))
            for review in reviews:
                payload[str(review["classification_key"])] = json_value(
                    str(review["classification_json"]),
                    {},
                )
            results = {
                key: ValidatedClassification.model_validate(value)
                for key, value in payload.items()
            }
            dataset = load_return_dataset(
                Path(str(task["return_file_path"])),
                Path(str(task["product_file_path"])),
                store=str(task["store"]),
                listing=task["listing"],
            )
            taxonomy = self.capability_registry.combined_taxonomy()
            next_version = int(task["result_version"]) + 1
            result_dir = Path(str(task["result_file_path"])).parent
            next_output = result_dir / f"analysis-v{next_version}.xlsx"
            next_json = result_dir / f"classifications-v{next_version}.json"
            export_results(next_output, dataset, results, taxonomy)
            next_json.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            metrics = json_value(task["metrics_json"], {})
            review_count = int(metrics.get("review_count", 0))
            resolved_count = int(resolved["count"])
            pending_count = max(review_count - resolved_count, 0)
            metrics["review_resolved"] = resolved_count
            metrics["statuses"] = dict(
                Counter(result.status.value for result in results.values())
            )
            metrics["top_problem_labels"] = self._top_problem_labels(
                dataset,
                results,
                taxonomy,
            )
            if pending_count:
                message = f"分析完成，{pending_count} 条结果需要人工复核"
            elif review_count:
                message = "分析完成，全部人工复核已处理"
            else:
                message = "分析完成，无需人工复核"
            now = utc_now()
            with self.database.transaction(immediate=True) as connection:
                connection.execute(
                    """
                    UPDATE tasks
                    SET result_file_path = ?, results_json_path = ?,
                        result_version = ?, metrics_json = ?, message = ?,
                        revision = revision + 1
                    WHERE id = ?
                    """,
                    (
                        str(next_output),
                        str(next_json),
                        next_version,
                        json_text(metrics),
                        message,
                        task_id,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO task_events(
                        task_id, event_type, stage, message,
                        data_json, actor_id, created_at
                    ) VALUES (?, 'review', '人工复核', ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        f"人工复核已写入结果版本 v{next_version}",
                        json_text({"result_version": next_version}),
                        actor_id,
                        now,
                    ),
                )

    @staticmethod
    def _top_problem_labels(dataset, results, taxonomy) -> list[dict[str, Any]]:
        labels = {label.code: label for label in taxonomy.labels}
        record_counts = dataset.records["classification_key"].value_counts()
        counts: Counter[str] = Counter()
        for key, result in results.items():
            weight = int(record_counts.get(key, 0))
            counts.update({code: weight for code in result.problem_label_codes})
        denominator = max(int(dataset.records["has_text_evidence"].sum()), 1)
        return [
            {
                "code": code,
                "name": labels[code].name,
                "group": labels[code].group,
                "count": count,
                "share": round(count / denominator * 100, 2),
            }
            for code, count in counts.most_common(8)
            if code in labels
        ]

    def _record_batch_conflict(
        self,
        batch_id: str,
        actor_id: str,
        message: str,
    ) -> None:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            batch = connection.execute(
                """
                SELECT b.revision, r.source_task_id
                FROM review_batches b
                JOIN classification_results r ON r.id = b.result_id
                WHERE b.id = ?
                """,
                (batch_id,),
            ).fetchone()
            if batch is None:
                return
            data = {"batch_id": batch_id, "message": message[:500]}
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'review_batch_conflict', '人工复核',
                          '复核批次操作冲突', ?, ?, ?)
                """,
                (
                    batch["source_task_id"],
                    actor_id,
                    json_text(data),
                    now,
                ),
            )
            self._insert_audit(
                connection,
                batch_id,
                "conflict",
                actor_id,
                {"revision": int(batch["revision"])},
                data,
                now,
            )

    @staticmethod
    def _version_quality(qualities: list[str]) -> str:
        if qualities and all(value == "unusable" for value in qualities):
            return "unusable"
        if any(value not in {"ready", "excluded"} for value in qualities):
            return "review_required"
        return "ready"

    @staticmethod
    def _insert_audit(
        connection: Any,
        batch_id: str,
        action: str,
        actor_id: str,
        before: dict[str, Any],
        after: dict[str, Any],
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_logs(
                id, entity_type, entity_id, action, before_json,
                after_json, actor_id, created_at
            ) VALUES (?, 'review_batch', ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("audit"),
                batch_id,
                action,
                json_text(before),
                json_text(after),
                actor_id,
                created_at,
            ),
        )

    @staticmethod
    def _serialize_batch(item: dict[str, Any]) -> dict[str, Any]:
        item["record_count"] = int(item.get("record_count") or 0)
        item["resolved_count"] = int(item.get("resolved_count") or 0)
        item["excluded_count"] = int(item.get("excluded_count") or 0)
        item["remaining_count"] = (
            item["record_count"] - item["resolved_count"] - item["excluded_count"]
        )
        item["creator"] = {
            "id": item.get("created_by"),
            "display_name": item.get("creator_name"),
        }
        return item

    @classmethod
    def _serialize_batch_record(cls, item: dict[str, Any]) -> dict[str, Any]:
        item = cls._serialize(item)
        for field in (
            "order_ids",
            "product_names",
            "listings",
            "source_skus",
            "matched_mskus",
            "product_skus",
        ):
            values = json_value(item.pop(f"{field}_json", None), [])
            item[field] = sorted(
                {
                    str(value).strip()
                    for value in values
                    if value is not None and str(value).strip()
                }
            )
        item["record_count"] = int(item.get("record_count") or 0)
        return item

    @staticmethod
    def _serialize(item: dict[str, Any]) -> dict[str, Any]:
        item["legacy"] = item.get("batch_id") is None
        item["classification"] = json_value(
            item.pop("classification_json", None),
            {},
        )
        return item

    @staticmethod
    def _serialize_revision(item: dict[str, Any]) -> dict[str, Any]:
        item["before"] = json_value(item.pop("before_json"), {})
        item["after"] = json_value(item.pop("after_json"), {})
        return item
