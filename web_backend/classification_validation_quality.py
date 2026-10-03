"""汇总参考比较并协调发布质量检查。"""

from collections import Counter
from typing import Any

from web_backend.classification_reference_scope import SCOPE_FIELDS as SCOPE_FIELDS
from web_backend.classification_standards.validation_facts import (
    _fact_pairs as _fact_pairs,
)
from web_backend.classification_standards.validation_facts import (
    append_reference_fact as append_reference_fact,
)
from web_backend.classification_standards.validation_quality_policy import (
    ERROR_METRICS as ERROR_METRICS,
)
from web_backend.classification_standards.validation_quality_policy import (
    FACT_QUALITY_POLICY as FACT_QUALITY_POLICY,
)
from web_backend.classification_standards.validation_quality_policy import (
    METRIC_LABELS as METRIC_LABELS,
)
from web_backend.classification_standards.validation_quality_policy import (
    quality_gate as quality_gate,
)
from web_backend.classification_standards.validation_reference_comparison import (
    compare_reference as compare_reference,
)


def evaluate_references(items: list[dict]) -> dict[str, Any]:
    judged = [
        item
        for item in items
        if item.get("reference") and not item["reference"]["ambiguous"]
    ]
    output: dict[str, Any] = {
        "sample_count": len(judged),
        "total_sample_count": len(items),
        "fact_state_sample_count": sum(
            bool(item["reference"].get("fact_state_complete")) for item in judged
        ),
        "scope_sample_counts": {
            dimension: sum(
                bool(item["reference"].get("scope_complete", {}).get(dimension))
                for item in judged
            )
            for dimension in SCOPE_FIELDS
        },
        "ambiguous_count": sum(
            bool(item.get("reference", {}).get("ambiguous"))
            for item in items
            if item.get("reference")
        ),
        "evidence_scope": "检查证据逐字存在且包含参考证据，允许连续扩展；未填写参考证据或观点推理是否充分仍需人工判断",
        "sides": {},
    }
    for side in ("baseline", "draft"):
        totals = Counter(
            dict.fromkeys(
                (
                    *ERROR_METRICS,
                    "exact_label_samples",
                    "expected_instances",
                    "actual_instances",
                    "matched_instances",
                ),
                0,
            )
        )
        for item in judged:
            comparison = compare_reference(item, side)
            item.setdefault("reference_comparison", {})[side] = comparison
            totals.update(comparison)
            totals["duplicate_samples"] += comparison["duplicate_units"] > 0
        output["sides"][side] = dict(totals)
    return output


def publication_quality_gate(
    snapshot: dict, source: dict, items: list, summary: dict
) -> dict:
    policy = source.get("quality_policy")
    if snapshot.get("taxonomy", {}).get("recognition_profile") == "fact_v2":
        policy = policy or FACT_QUALITY_POLICY
    if items:
        summary = {**summary, "reference_evaluation": evaluate_references(items)}
    return quality_gate(summary, policy)
