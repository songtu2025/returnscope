"""按反馈组的源明细范围核对人工修正历史，禁止跨组还原。"""

from dataclasses import dataclass
from typing import Any

from web_backend.common import json_value


@dataclass(frozen=True)
class SemanticRestore:
    """还原一条人工修改记录，复用反馈组的保存事务。"""

    audit_id: str


def correction_history(
    connection: Any, result_id: str, source_rows: list[int]
) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT a.*, u.display_name FROM audit_logs a JOIN users u ON u.id=a.actor_id "
        "WHERE a.entity_type='classification_result' AND a.entity_id=? "
        "AND a.action IN ('manual_correction', 'semantic_restore') "
        "ORDER BY a.created_at DESC, a.id DESC",
        (result_id,),
    ).fetchall()
    output = []
    for row in rows:
        after = json_value(row["after_json"], {})
        if sorted(after.get("source_rows", [])) == sorted(source_rows):
            output.append(
                {
                    "id": row["id"],
                    "created_at": row["created_at"],
                    "actor_name": row["display_name"],
                    "before": json_value(row["before_json"], {}).get(
                        "classification", {}
                    ),
                    "after": after.get("classification", {}),
                }
            )
    return output


def restored_classification(
    connection: Any,
    result_id: str,
    source_rows: list[int],
    audit_id: str,
    taxonomy: Any,
) -> dict[str, Any]:
    entry = next(
        (
            item
            for item in correction_history(connection, result_id, source_rows)
            if item["id"] == audit_id
        ),
        None,
    )
    if entry is None:
        raise ValueError("当前反馈组的修改记录不存在")
    restored = entry["before"]
    codes = set(restored.get("primary_label_codes", [])) | {
        unit["label_code"] for unit in restored.get("semantic_units", [])
    }
    if codes - {label.code for label in taxonomy.labels}:
        raise ValueError("历史标签已不适用于当前结果，请人工修正")
    restored["status"] = "MANUAL_RESOLVED"
    restored["review_reasons"] = []
    restored["human_review_assessment"] = {"resolved": True}
    return restored
