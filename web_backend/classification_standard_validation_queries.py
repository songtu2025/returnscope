from __future__ import annotations

from typing import Any

from return_semantics.prompt import validation_contract_matches
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.classification_standard_validation_contracts import (
    ClassificationStandardValidationNotFound,
)
from web_backend.classification_validation_quality import (
    evaluate_references,
    publication_quality_gate,
)
from web_backend.common import json_value
from web_backend.database import Database


class ClassificationStandardValidationQueriesMixin:
    database: Database
    standard_service: ClassificationStandardService

    def list_runs(self, draft_id: str) -> list[dict[str, Any]]:
        self.standard_service.get_draft(draft_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM classification_standard_validation_runs
                WHERE draft_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 20
                """,
                (draft_id,),
            ).fetchall()
        return [self._serialize(dict(row)) for row in rows]

    def get(self, run_id: str, include_items: bool = True) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM classification_standard_validation_runs
                WHERE id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            raise ClassificationStandardValidationNotFound("样本验证任务不存在")
        return self._serialize(dict(row), include_items=include_items)

    def _serialize(
        self,
        value: dict[str, Any],
        include_items: bool = False,
    ) -> dict[str, Any]:
        source = json_value(value.pop("source_json"), {})
        snapshot = json_value(value.pop("snapshot_json", None), {})
        value.pop("sample_json", None)
        items = json_value(value.pop("result_json"), [])
        value["summary"] = json_value(value.pop("summary_json"), {})
        value["usage"] = json_value(value.pop("usage_json"), {})
        value["metrics"] = json_value(value.pop("metrics_json"), {})
        value["model_names"] = json_value(value.pop("model_names_json"), [])
        value["source"] = source.get("result", {})
        if include_items:
            value["items"] = items
        with self.database.connect() as connection:
            draft = connection.execute(
                """
                SELECT revision FROM classification_standard_drafts WHERE id = ?
                """,
                (value["draft_id"],),
            ).fetchone()
            approver = (
                connection.execute(
                    "SELECT display_name FROM users WHERE id = ?",
                    (value.get("approved_by"),),
                ).fetchone()
                if value.get("approved_by")
                else None
            )
        value["approved_by_name"] = (
            str(approver["display_name"]) if approver is not None else None
        )
        value["is_current"] = bool(
            draft
            and int(draft["revision"]) == int(value["draft_revision"])
            and (
                source.get("comparison_type", "standard_version") != "standard_version"
                or validation_contract_matches(snapshot, source)
            )
        )
        if items:
            value["summary"]["reference_evaluation"] = evaluate_references(items)
            if source.get("comparison_type", "standard_version") == "standard_version":
                value["summary"]["reference_evaluation"]["sides"].pop("baseline", None)
        value["quality_gate"] = publication_quality_gate(
            snapshot, source, [], value["summary"]
        )
        value["publication_ready"] = bool(
            value["quality_gate"]["passed"]
            and value["is_current"]
            and value["status"] == "completed"
            and int(value["error_count"]) == 0
            and bool(value.get("approved_at"))
            and source.get("comparison_type", "standard_version") == "standard_version"
        )
        return value
