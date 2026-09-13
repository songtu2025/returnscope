from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterator

MIN_IDENTIFIER_LENGTH = 8
MIN_COMPARABLE_TEXT_LENGTH = 48
HIGH_OVERLAP_RATIO = 0.88
TEXT_SHINGLE_SIZE = 3
MAX_REPORTED_GROUPS = 8


def find_taxonomy_sample_leaks(
    taxonomy: dict[str, Any],
    samples: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """检查标签定义是否包含当前验证样本的编号或长文本。"""
    issues: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    fields = [
        (*field, *_text_fingerprint(field[2])) for field in _taxonomy_fields(taxonomy)
    ]
    for sample in samples:
        review_id = str(sample.get("review_id") or "").strip()
        comment = str(sample.get("comment") or "").strip()
        normalized_comment, comment_shingles = _text_fingerprint(comment)
        for label, field, value, normalized_value, value_shingles in fields:
            match_type = _match_type(
                value,
                normalized_value,
                value_shingles,
                review_id,
                normalized_comment,
                comment_shingles,
            )
            if match_type is None:
                continue
            key = (str(label.get("code") or ""), field, review_id, match_type)
            if key in seen:
                continue
            seen.add(key)
            issues.append(
                {
                    "label_code": str(label.get("code") or ""),
                    "label_name": str(label.get("name") or "未命名标签"),
                    "field": field,
                    "review_id": review_id or "未提供编号",
                    "match_type": match_type,
                }
            )
    return issues


def format_taxonomy_sample_leaks(issues: list[dict[str, str]]) -> str:
    """生成可直接定位并修复的阻断信息。"""
    grouped: dict[tuple[str, str, str], list[str]] = {}
    for issue in issues:
        key = (issue["label_name"], issue["label_code"], issue["review_id"])
        grouped.setdefault(key, []).append(issue["field"])
    details = []
    for (label_name, label_code, review_id), fields in list(grouped.items())[
        :MAX_REPORTED_GROUPS
    ]:
        details.append(
            f"标签“{label_name}”（{label_code}）的"
            f"{'、'.join(dict.fromkeys(fields))}包含验证样本 {review_id} 的编号或长文本"
        )
    remaining = len(grouped) - len(details)
    suffix = f"；另有 {remaining} 个标签/样本组合" if remaining > 0 else ""
    return (
        "标签体系与当前验证样本存在数据泄漏："
        + "；".join(details)
        + suffix
        + "。请删除真实评论编号和原句，改用独立编写的通用示例后重新验证"
    )


def _taxonomy_fields(
    taxonomy: dict[str, Any],
) -> Iterator[tuple[dict[str, Any], str, str]]:
    for label in taxonomy.get("labels", []):
        yield label, "标签名称", str(label.get("name") or "")
        yield label, "判定定义", str(label.get("description") or "")
        for index, exclusion in enumerate(label.get("exclusions", []), start=1):
            yield label, f"不适用条件 {index}", str(exclusion or "")
        for index, example in enumerate(label.get("examples", []), start=1):
            yield label, f"示例 {index} 原文", str(example.get("text") or "")
            yield label, f"示例 {index} 说明", str(example.get("explanation") or "")


def _match_type(
    value: str,
    normalized_value: str,
    value_shingles: set[str],
    review_id: str,
    normalized_comment: str,
    comment_shingles: set[str],
) -> str | None:
    if _contains_sample_identifier(value, review_id):
        return "review_id"
    if _has_high_text_overlap(
        normalized_value,
        value_shingles,
        normalized_comment,
        comment_shingles,
    ):
        return "long_text"
    return None


def _contains_sample_identifier(value: str, review_id: str) -> bool:
    compact_id = review_id.strip()
    if (
        len(compact_id) < MIN_IDENTIFIER_LENGTH
        or not any(character.isalpha() for character in compact_id)
        or not any(character.isdigit() for character in compact_id)
    ):
        return False
    pattern = rf"(?<![0-9a-z]){re.escape(compact_id.casefold())}(?![0-9a-z])"
    return re.search(pattern, value.casefold()) is not None


def _has_high_text_overlap(
    normalized_value: str,
    value_shingles: set[str],
    normalized_comment: str,
    comment_shingles: set[str],
) -> bool:
    shorter_length = min(len(normalized_value), len(normalized_comment))
    if shorter_length < MIN_COMPARABLE_TEXT_LENGTH:
        return False
    if normalized_value in normalized_comment or normalized_comment in normalized_value:
        return True
    shorter_shingle_count = min(len(value_shingles), len(comment_shingles))
    if not shorter_shingle_count:
        return False
    overlap = len(value_shingles & comment_shingles) / shorter_shingle_count
    return overlap >= HIGH_OVERLAP_RATIO


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _text_fingerprint(value: str) -> tuple[str, set[str]]:
    normalized = _normalize_text(value)
    shingles = {
        normalized[index : index + TEXT_SHINGLE_SIZE]
        for index in range(len(normalized) - TEXT_SHINGLE_SIZE + 1)
    }
    return normalized, shingles
