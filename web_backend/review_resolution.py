from __future__ import annotations

import json
from builtins import list as builtin_list
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

from return_semantics.data import load_return_dataset
from return_semantics.exporter import export_results
from return_semantics.schemas import ValidatedClassification
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.common import add_audit, json_text, json_value, new_id
from web_backend.database import Database
from web_backend.review_contracts import RevisionConflict, _task_lock
from web_backend.security import utc_now


class ReviewResolutionMixin:
    database: Database
    standard_service: ClassificationStandardService

    if TYPE_CHECKING:

        def get(self, review_id: str) -> dict[str, Any] | None: ...

        def _apply_resolution(
            self,
            classification: dict[str, Any],
            comment: str,
            label_code: str | None,
            result_version_id: str | None = None,
        ) -> dict[str, Any]: ...

        def _validate_reviewed_classification(
            self,
            classification: dict[str, Any],
        ) -> tuple[ValidatedClassification, dict[str, Any] | None]: ...

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
            after = self._apply_resolution(
                before,
                str(row["comment"]),
                label_code,
                str(row["base_result_version_id"] or "") or None,
            )
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
                key: self._validate_reviewed_classification(value)[0]
                for key, value in payload.items()
            }
            dataset = load_return_dataset(
                Path(str(task["return_file_path"])),
                Path(str(task["product_file_path"])),
                store=str(task["store"]),
                listing=task["listing"],
            )
            taxonomy = self.standard_service.combined_taxonomy()
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
    def _top_problem_labels(dataset, results, taxonomy) -> builtin_list[dict[str, Any]]:
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
