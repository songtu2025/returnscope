from __future__ import annotations

from typing import Any


def source_quality_issues(
    product_mapping: dict[str, Any],
    review_bias: dict[str, Any],
    pending_count: int,
    *,
    mapping_trusted: bool,
) -> list[dict[str, Any]]:
    source_issues: list[dict[str, Any]] = []
    if not mapping_trusted:
        source_issues.append(
            {
                "code": "product_mapping",
                "label": "商品主数据需核对",
                "detail": str(
                    product_mapping.get("note") or "商品主数据映射需要核对。"
                ),
                "evidence_ids": ["product_mapping", "scope"],
            }
        )
    if pending_count:
        source_issues.append(
            {
                "code": "pending_review",
                "label": "存在待审核记录",
                "detail": str(
                    review_bias.get("note")
                    or f"{pending_count} 条待审核记录未进入本次统计。"
                ),
                "evidence_ids": ["scope", "review_bias"],
            }
        )
    return source_issues
