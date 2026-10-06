from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _node_code(namespace: str, kind: str, path: tuple[str, ...]) -> str:
    identity = "\x1f".join((namespace, kind, *path))
    return f"{kind}_{hashlib.sha256(identity.encode()).hexdigest()[:20].upper()}"


def _existing_paths(content: dict[str, Any]) -> tuple[dict, dict]:
    categories = {item["code"]: item for item in content.get("categories", [])}

    def path(item: dict[str, Any]) -> tuple[str, ...]:
        names = [item["name"]]
        parent = _text(item.get("parent_code"))
        visited: set[str] = set()
        while parent in categories and parent not in visited:
            visited.add(parent)
            category = categories[parent]
            names.insert(0, category["name"])
            parent = _text(category.get("parent_code"))
        return tuple(names)

    category_paths = {path(item): item for item in categories.values()}
    label_items = (
        content.get("labels", []) if content.get("structure_version") == 2 else []
    )
    label_paths = {path(item): item for item in label_items}
    if len(category_paths) != len(categories) or len(label_paths) != len(label_items):
        raise ValueError("现有草稿中同一路径存在多个编码，请先修复重复节点后再导入")
    return category_paths, label_paths


def row_path(
    row: list[str],
    indices: list[int],
    number: int,
    issues: list[dict[str, Any]],
) -> tuple[str, ...] | None:
    path = tuple(row[index] for index in indices)
    while path and not path[-1]:
        path = path[:-1]
    if len(path) < 2 or any(not name for name in path):
        issues.append(
            {
                "severity": "blocking",
                "row": number,
                "message": "至少需要分类和末端标签，且不能缺失中间层级",
            }
        )
        return None
    return path


def category_parent(
    path: tuple[str, ...],
    old_categories: dict[tuple[str, ...], dict[str, Any]],
    categories: dict[tuple[str, ...], dict[str, Any]],
    namespace: str,
) -> str | None:
    parent = None
    for depth in range(1, len(path)):
        prefix = path[:depth]
        categories.setdefault(
            prefix,
            {
                "code": old_categories.get(prefix, {}).get("code")
                or _node_code(namespace, "CAT", prefix),
                "name": prefix[-1],
                "parent_code": parent,
            },
        )
        parent = categories[prefix]["code"]
    return parent


def label_for_path(
    path: tuple[str, ...],
    parent: str | None,
    sentiments: list[str],
    original: dict[str, Any] | None,
    namespace: str,
) -> dict[str, Any]:
    label = deepcopy(original) or {
        "code": _node_code(namespace, "LABEL", path),
        "description": "",
        "keywords": [],
        "exclusions": [],
        "examples": [],
        "allowed_claim_ids": [],
    }
    label.update(
        name=path[-1],
        parent_code=parent,
        group=path[0],
        allowed_sentiments=sentiments,
    )
    return label


def reconcile_sentiments(
    existing: dict[str, Any] | None,
    sentiments: list[str],
    number: int,
    issues: list[dict[str, Any]],
) -> None:
    if existing and existing["allowed_sentiments"] != sentiments:
        issues.append(
            {
                "severity": "warning"
                if not sentiments or not existing["allowed_sentiments"]
                else "blocking",
                "row": number,
                "message": "同一路径的评价方向冲突或未明确，已清空该标签方向，请核对所有来源后选择",
            }
        )
        existing["allowed_sentiments"] = []
