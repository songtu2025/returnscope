from __future__ import annotations

from typing import Any

from return_semantics.semantic_review import requires_system_rerun
from web_backend.classification_unit_semantics import refresh_unit_semantics
from web_backend.common import json_text, new_id


def insert_units(
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
        [unit_values(version_id, value) for value in units],
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

    refresh_unit_semantics(connection, version_id)


def unit_values(version_id: str, value: dict[str, Any]) -> tuple[Any, ...]:
    return (
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
