"""数据库中的当前结果决定重跑范围，检查点不覆盖人工结论。"""

from typing import Any

from return_semantics.schemas import ValidatedClassification
from web_backend.classification_results.effective_content import load_content


def current_inherited_results(
    database: Any, version_id: str
) -> dict[str, ValidatedClassification]:
    with database.connect() as connection:
        content = load_content(connection, version_id)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for unit in content["units"]:
        assessment = unit["classification"].get("human_review_assessment", {})
        key = assessment.get("original_classification_key", unit["classification_key"])
        grouped.setdefault(key, []).append(unit)
    results = {}
    for key, units in grouped.items():
        if any(unit["system_rerun_required"] for unit in units):
            continue
        # 同键存在多个人工反馈时，运行检查点只需占位；发布时按源明细恢复所有人工结果。
        unit = next(
            (unit for unit in units if unit["classification_key"] == key), units[0]
        )
        fields = {
            name: value
            for name, value in unit["classification"].items()
            if name in ValidatedClassification.model_fields
        }
        results[key] = ValidatedClassification.model_validate(
            {**fields, "classification_key": key}
        )
    return results
