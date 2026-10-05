"""读取、导出和发布旧版人工复核的任务结果。"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

from return_semantics.data import ReturnDataset, load_return_dataset
from return_semantics.exporter import export_results
from return_semantics.schemas import TaxonomyConfig, ValidatedClassification
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.common import json_text, json_value
from web_backend.database import Database
from web_backend.review_contracts import _task_lock
from web_backend.security import utc_now


class ReviewLegacyResultRebuildMixin:
    database: Database
    standard_service: ClassificationStandardService

    if TYPE_CHECKING:

        def _validate_reviewed_classification(
            self, classification: dict[str, Any]
        ) -> tuple[ValidatedClassification, dict[str, Any]]: ...

        @staticmethod
        def _top_problem_labels(
            dataset: ReturnDataset,
            results: dict[str, ValidatedClassification],
            taxonomy: TaxonomyConfig,
        ) -> list[dict[str, Any]]: ...

    def _rebuild_result(self, task_id: str, actor_id: str) -> None:
        with _task_lock(task_id):
            task, reviews, resolved = self._read_rebuild_inputs(task_id)
            if task is None or not task["results_json_path"]:
                raise ValueError("任务结果尚未生成")
            payload, results, dataset, taxonomy = self._prepare_rebuild_classifications(
                task, reviews
            )
            next_version, next_output, next_json = self._export_rebuilt_result(
                task, payload, results, dataset, taxonomy
            )
            metrics, message = self._rebuilt_result_summary(
                task, resolved, results, dataset, taxonomy
            )
            self._publish_rebuilt_result(
                task_id,
                actor_id,
                next_version,
                (next_output, next_json),
                (metrics, message),
            )

    def _read_rebuild_inputs(self, task_id: str) -> tuple[Any, list[Any], Any]:
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
        return task, reviews, resolved

    def _prepare_rebuild_classifications(
        self, task: Any, reviews: list[Any]
    ) -> tuple[
        dict[str, Any],
        dict[str, ValidatedClassification],
        ReturnDataset,
        TaxonomyConfig,
    ]:
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
        return payload, results, dataset, taxonomy

    @staticmethod
    def _export_rebuilt_result(
        task: Any,
        payload: dict[str, Any],
        results: dict[str, ValidatedClassification],
        dataset: ReturnDataset,
        taxonomy: TaxonomyConfig,
    ) -> tuple[int, Path, Path]:
        next_version = int(task["result_version"]) + 1
        result_dir = Path(str(task["result_file_path"])).parent
        next_output = result_dir / f"analysis-v{next_version}.xlsx"
        next_json = result_dir / f"classifications-v{next_version}.json"
        export_results(next_output, dataset, results, taxonomy)
        next_json.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        return next_version, next_output, next_json

    def _rebuilt_result_summary(
        self,
        task: Any,
        resolved: Any,
        results: dict[str, ValidatedClassification],
        dataset: ReturnDataset,
        taxonomy: TaxonomyConfig,
    ) -> tuple[dict[str, Any], str]:
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
        return metrics, message

    def _publish_rebuilt_result(
        self,
        task_id: str,
        actor_id: str,
        next_version: int,
        output_paths: tuple[Path, Path],
        result_summary: tuple[dict[str, Any], str],
    ) -> None:
        next_output, next_json = output_paths
        metrics, message = result_summary
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
