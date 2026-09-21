from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from return_semantics.exporter import REVIEW_STATUSES
from return_semantics.schemas import ProcessingStatus, TaxonomyConfig
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.classification_validation_quality import evaluate_references
from web_backend.common import json_text, json_value
from web_backend.database import Database
from web_backend.security import utc_now

if TYPE_CHECKING:
    from web_backend.agent_runner import AgentRunner


class ClassificationStandardValidationExecutionMixin:
    database: Database
    standard_service: ClassificationStandardService
    runner: AgentRunner

    _evaluate_references = staticmethod(evaluate_references)

    def run(self, run_id: str) -> None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM classification_standard_validation_runs
                WHERE id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None or row["status"] != "running":
            return
        validation = dict(row)
        samples = json_value(validation["sample_json"], [])
        source = json_value(validation["source_json"], {})
        snapshot = json_value(validation["snapshot_json"], {})
        taxonomy_data = deepcopy(
            source.get("recognition_taxonomies", {}).get(
                "candidate", snapshot["taxonomy"]
            )
        )
        taxonomy_data["version"] = (
            f"draft-{validation['draft_id']}-r{validation['draft_revision']}"
        )
        try:
            taxonomy = TaxonomyConfig.model_validate(taxonomy_data)

            stage = "calling_model"

            def progress(current: int, total: int) -> None:
                if current == 1 or current == total or current % 5 == 0:
                    with self.database.transaction() as connection:
                        connection.execute(
                            """
                            UPDATE classification_standard_validation_runs
                            SET processed_count = ?, stage = ?
                            WHERE id = ? AND status = 'running'
                            """,
                            (current, stage, run_id),
                        )

            if (
                source.get("kind") in {"raw_dataset", "review_file"}
                or source.get("comparison_type", "standard_version")
                != "standard_version"
            ) and source.get("result", {}).get(
                "comparison_mode"
            ) == "baseline_and_draft":
                base_taxonomy = (
                    TaxonomyConfig.model_validate(
                        source["recognition_taxonomies"]["baseline"]
                    )
                    if source.get("recognition_taxonomies")
                    else self.standard_service.taxonomy_for_version(
                        str(validation["base_version_id"])
                    )
                )
                stage = "comparing_baseline"
                progress(0, len(samples))
                baseline_pipeline = self.runner.classify_taxonomy_sample(
                    taxonomy=base_taxonomy,
                    samples=samples,
                    source=source,
                    progress=progress,
                )
                for sample in samples:
                    key = str(sample["classification_key"])
                    sample["baseline"] = baseline_pipeline.classifications[
                        key
                    ].model_dump(mode="json")
            else:
                baseline_pipeline = None

            stage = "calling_model"
            progress(0, len(samples))
            pipeline = self.runner.classify_taxonomy_sample(
                taxonomy=taxonomy,
                samples=samples,
                source=source,
                progress=progress,
            )
            items = self._comparison_items(samples, pipeline.classifications)
            summary = self._summary(items)
            summary["reference_evaluation"] = self._evaluate_references(items)
            if source.get("comparison_type", "standard_version") == "standard_version":
                summary["reference_evaluation"]["sides"].pop("baseline", None)
            model_names = sorted(
                {
                    str(item["draft"]["model_name"])
                    for item in items
                    if item["draft"].get("model_name")
                }
                | {
                    str(result.model_name)
                    for result in (
                        baseline_pipeline.classifications.values()
                        if baseline_pipeline is not None
                        else []
                    )
                    if result.model_name
                }
            )
            with self.database.transaction(immediate=True) as connection:
                connection.execute(
                    """
                    UPDATE classification_standard_validation_runs
                    SET status = 'completed', stage = 'completed',
                        processed_count = sample_size, changed_count = ?,
                        unknown_count = ?, review_count = ?, error_count = ?,
                        result_json = ?, summary_json = ?, usage_json = ?,
                        metrics_json = ?, model_names_json = ?,
                        error = NULL, completed_at = ?
                    WHERE id = ? AND status = 'running'
                    """,
                    (
                        summary["changed_count"],
                        summary["unknown_count"],
                        summary["review_count"],
                        summary["error_count"],
                        json_text(items),
                        json_text(summary),
                        json_text(
                            {
                                "baseline": (
                                    baseline_pipeline.usage
                                    if baseline_pipeline is not None
                                    else {}
                                ),
                                "draft": pipeline.usage,
                            }
                        ),
                        json_text(
                            {
                                "baseline": (
                                    baseline_pipeline.request_metrics
                                    if baseline_pipeline is not None
                                    else {}
                                ),
                                "draft": pipeline.request_metrics,
                            }
                        ),
                        json_text(model_names),
                        utc_now(),
                        run_id,
                    ),
                )
        except Exception as exc:
            with self.database.transaction(immediate=True) as connection:
                connection.execute(
                    """
                    UPDATE classification_standard_validation_runs
                    SET status = 'failed', stage = 'failed', error = ?,
                        completed_at = ?
                    WHERE id = ? AND status = 'running'
                    """,
                    (str(exc)[:2000], utc_now(), run_id),
                )

    @staticmethod
    def _comparison_items(
        samples: list[dict[str, Any]],
        classifications: dict[str, Any],
    ) -> list[dict[str, Any]]:
        output = []
        for sample in samples:
            key = str(sample["classification_key"])
            result = classifications[key].model_dump(mode="json")
            baseline_labels = sorted(sample["baseline"].get("primary_label_codes", []))
            draft_labels = sorted(result.get("primary_label_codes", []))

            def signature(units):
                return sorted(
                    {
                        (unit["label_code"], unit.get("sentiment"), unit.get("part"))
                        for unit in units
                    }
                )

            semantic_changed = signature(
                sample["baseline"].get("semantic_units", [])
            ) != signature(result.get("semantic_units", []))
            primary_changed = baseline_labels != draft_labels
            output.append(
                {
                    "classification_key": key,
                    "comment": sample["comment"],
                    "reference": sample.get("reference"),
                    "category_a": sample["category_a"],
                    "category_b": sample["category_b"],
                    "baseline": {
                        "extracted_facts": sample["baseline"].get(
                            "extracted_facts", []
                        ),
                        "fact_mappings": sample["baseline"].get("fact_mappings", []),
                        "primary_label_codes": baseline_labels,
                        "semantic_units": sample["baseline"].get("semantic_units", []),
                        "unknown_semantics": sample["baseline"].get(
                            "unknown_semantics", []
                        ),
                        "status": sample["baseline"].get("status"),
                        "review_reasons": sample["baseline"].get("review_reasons", []),
                        "reason": sample.get("reason"),
                    },
                    "draft": {
                        "extracted_facts": result.get("extracted_facts", []),
                        "fact_mappings": result.get("fact_mappings", []),
                        "primary_label_codes": draft_labels,
                        "status": result["status"],
                        "unknown_semantics": result.get("unknown_semantics", []),
                        "semantic_units": [
                            {
                                "label_code": unit["label_code"],
                                "opinion": unit["opinion"],
                                "evidence": unit["evidence"],
                                "sentiment": unit["sentiment"],
                                "part": unit["part"],
                            }
                            for unit in result.get("semantic_units", [])
                        ],
                        "review_reasons": result.get("review_reasons", []),
                        "model_name": result.get("model_name"),
                    },
                    "semantic_changed": semantic_changed,
                    "primary_changed": primary_changed,
                    "changed": semantic_changed or primary_changed,
                }
            )
        return output

    @staticmethod
    def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(items)
        changed_count = sum(bool(item["changed"]) for item in items)
        semantic_changed_count = sum(
            bool(item.get("semantic_changed")) for item in items
        )
        primary_changed_count = sum(bool(item.get("primary_changed")) for item in items)
        unknown_count = sum(bool(item["draft"]["unknown_semantics"]) for item in items)
        review_count = sum(
            str(item["draft"]["status"]) in REVIEW_STATUSES for item in items
        )
        error_count = sum(
            str(item["draft"]["status"]) == ProcessingStatus.MODEL_ERROR.value
            or str(item["baseline"].get("status")) == ProcessingStatus.MODEL_ERROR.value
            for item in items
        )
        coverage_count = sum(bool(item["draft"]["semantic_units"]) for item in items)

        def rate(value: int) -> float:
            return round(value / total * 100, 1) if total else 0.0

        return {
            "sample_size": total,
            "changed_count": changed_count,
            "changed_rate": rate(changed_count),
            "semantic_changed_count": semantic_changed_count,
            "semantic_changed_rate": rate(semantic_changed_count),
            "primary_changed_count": primary_changed_count,
            "primary_changed_rate": rate(primary_changed_count),
            "coverage_count": coverage_count,
            "coverage_rate": rate(coverage_count),
            "unknown_count": unknown_count,
            "unknown_rate": rate(unknown_count),
            "review_count": review_count,
            "review_rate": rate(review_count),
            "error_count": error_count,
            "error_rate": rate(error_count),
        }
