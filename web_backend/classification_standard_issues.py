from __future__ import annotations

from typing import Any


def label_field_issues(taxonomy: dict[str, Any]) -> list[dict[str, Any]]:
    """返回可定位的字段问题；草稿允许不完整，发布时必须修正。"""
    issues = []
    fields = {
        "code": "编码",
        "name": "名称",
        "group": "分组",
        "allowed_sentiments": "适用情感",
    }
    kinds = {
        "allowed_sentiments": "missing_sentiment",
    }
    required = taxonomy.get("validation_rules", {}).get("boundary_required_labels", [])
    for index, label in enumerate(taxonomy.get("labels", [])):
        for field, title in fields.items():
            value = label.get(field)
            missing = (
                not value
                if field == "allowed_sentiments"
                else not str(value or "").strip()
            )
            if not missing:
                continue
            name = label.get("name") or label.get("code") or f"第 {index + 1} 个标签"
            detail = (
                "至少需要一种适用情感"
                if field == "allowed_sentiments"
                else f"缺少{title}"
            )
            issues.append(
                {
                    "kind": kinds.get(field, "missing_field"),
                    "message": f"{name}：{detail}",
                    "label_code": label.get("code", ""),
                    "label_index": index,
                    "field": field,
                }
            )
        if label.get("code") in required:
            issues.extend(_label_boundary_issues(label, index))
    return issues


def _label_boundary_issues(label: dict[str, Any], index: int) -> list[dict[str, Any]]:
    """只对标准显式要求的混淆标签检查边界完整性，不代替业务语义判断。"""
    name = label.get("name") or label.get("code") or f"第 {index + 1} 个标签"
    examples = label.get("examples", [])
    checks = {
        "exclusions": (
            any(str(value).strip() for value in label.get("exclusions", [])),
            "需补充至少一条不适用条件，说明与易混淆标签的边界",
        ),
        "examples": (
            all(
                any(
                    item.get("applies") is applies
                    and str(item.get("text", "")).strip()
                    and str(item.get("explanation", "")).strip()
                    for item in examples
                )
                for applies in (True, False)
            ),
            "需各补充一条适用和不适用示例，并说明判定原因",
        ),
    }
    return [
        {
            "kind": "missing_boundary",
            "message": f"{name}：{message}",
            "label_code": label.get("code", ""),
            "label_index": index,
            "field": field,
        }
        for field, (complete, message) in checks.items()
        if not complete
    ]
