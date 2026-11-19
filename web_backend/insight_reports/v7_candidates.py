from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal, NamedTuple

from web_backend.dashboard_support import percentage

InsightKind = Literal["risk", "polarization", "opportunity", "data_gap"]
KINDS: tuple[InsightKind, ...] = ("risk", "polarization", "opportunity", "data_gap")
MIN_SAMPLES = 10


class Candidate(NamedTuple):
    kind: InsightKind
    code: str
    title: str
    signal_count: int
    facts: list[str]
    extra_evidence: tuple[str, ...] = ()
    reason_code: str | None = None
    counts: dict[str, int] | None = None


def _label_candidates(
    labels: list[dict[str, Any]], taxonomy: dict[str, str]
) -> list[Candidate]:
    result = []
    for label in labels:
        code = label["code"]
        name = label["label"] or taxonomy.get(code) or code
        positive, negative = label["positive"], label["negative"]
        if negative:
            result.append(
                Candidate("risk", code, name + "的负向反馈", negative, [], (), code)
            )
        if positive and negative:
            result.append(
                Candidate(
                    "polarization",
                    code,
                    name + "的正负评价分化",
                    label["matched"],
                    [
                        f"正向 {positive} 条，负向 {negative} 条，同一条反馈可同时出现两种评价。"
                    ],
                )
            )
        if positive:
            result.append(
                Candidate("opportunity", code, name + "的正向反馈", positive, [])
            )
    return result


def select_candidates(
    analysis: dict[str, Any], source: dict[str, Any]
) -> list[Candidate]:
    signals = analysis["report_signals"]
    overview = signals["overview"]
    taxonomy = {
        item["code"]: item["name"]
        for item in (analysis.get("taxonomy") or {}).get("labels", [])
    }
    candidates = _label_candidates(signals["labels"], taxonomy)
    candidates.extend(
        _paired_candidates(
            signals, taxonomy, source["report_profile"]["polarization_pairs"]
        )
    )
    candidates.extend(_unlabeled_direction_candidates(candidates, overview))
    if overview["mixed"] and not any(
        item.kind == "polarization" for item in candidates
    ):
        candidates.append(
            Candidate(
                "polarization",
                "mixed",
                "同一反馈中并存正负评价",
                overview["mixed"],
                ["按整条反馈识别正负并存，涉及的标签可能不同。"],
            )
        )
    candidates.extend(_gap_candidates(source, overview))
    groups: dict[InsightKind, list[Candidate]] = defaultdict(list)
    for item in candidates:
        groups[item.kind].append(item)
    for group in groups.values():
        group.sort(key=lambda item: (-item.signal_count, item.code))
    # 先让每类最主要的信号进入摘要，再为各类保留第二条。
    return [
        groups[kind][index]
        for index in range(2)
        for kind in KINDS
        if len(groups[kind]) > index
    ]


def _paired_candidates(
    signals: dict[str, Any], taxonomy: dict[str, str], configured_pairs: list[Any]
) -> list[Candidate]:
    names = {
        label["code"]: label["label"] or taxonomy.get(label["code"])
        for label in signals["labels"]
    }
    candidates = []
    for pair in signals.get("paired_labels", []):
        directions = pair["directions"]
        if directions not in configured_pairs or not (
            pair["left_count"] and pair["right_count"]
        ):
            continue
        left, right = (
            next((names[code] for code in codes if names.get(code)), codes[0])
            for codes in directions
        )
        counts = {
            key: pair[key]
            for key in ("left_count", "right_count", "overlap", "union_count")
        }
        candidates.append(
            Candidate(
                "polarization",
                f"pair.{directions[0][0]}.{directions[1][0]}",
                f"{left}与{right}的反馈分化",
                counts["union_count"],
                [
                    f"{left} {counts['left_count']} 条，{right} {counts['right_count']} 条。",
                    f"同时命中两个方向 {counts['overlap']} 条，按反馈去重。",
                ],
                counts=counts,
            )
        )
    return candidates


def _unlabeled_direction_candidates(
    candidates: list[Candidate], overview: dict[str, int]
) -> list[Candidate]:
    findings: list[tuple[InsightKind, str, str]] = [
        ("risk", "negative", "存在未定位标签的负向评价"),
        ("opportunity", "positive", "存在未定位标签的正向评价"),
    ]
    labeled_kinds = {item.kind for item in candidates}
    return [
        Candidate(
            kind,
            direction,
            title,
            overview[direction] + overview["mixed"],
            [
                "评价方向已有记录，具体原因或优势还需结合原始反馈定位。",
            ],
        )
        for kind, direction, title in findings
        if kind not in labeled_kinds and (overview[direction] or overview["mixed"])
    ]


def _gap_candidates(
    source: dict[str, Any], overview: dict[str, int]
) -> list[Candidate]:
    mapping = source["product_mapping"]
    text = source["text_quality"]
    rows = [
        (
            "scope",
            "样本量较少",
            overview["total"] if overview["total"] < MIN_SAMPLES else 0,
            "样本量较少，需补充同口径反馈。",
        ),
        (
            "pending_review",
            "存在待复核反馈",
            source["pending_review_record_count"],
            "复核完成后重新核对信号分布。",
        ),
        (
            "product_mapping",
            "商品映射需补齐",
            max(
                mapping["unmatched_record_count"], mapping["missing_name_record_count"]
            ),
            mapping["note"],
        ),
        (
            "text_quality",
            "存在文本质量异常",
            text.get("anomaly_record_count", 0),
            text.get("note") or "请核对文本质量。",
        ),
        (
            "unclear",
            "无明确正负评价",
            overview["unclear"],
            "这些反馈未提供明确的正负评价信号。",
        ),
        (
            "unlabeled",
            "部分反馈没有标签",
            overview["total"] - overview["labeled"],
            "建议核对未打标签的原始反馈与分类范围。",
        ),
    ]
    evidence_keys = {
        "pending_review": "review_bias",
        "product_mapping": "product_mapping",
        "text_quality": "text_quality",
    }
    return [
        Candidate(
            "data_gap", code, title, count, [note], (evidence_keys.get(code, "scope"),)
        )
        for code, title, count, note in rows
        if count or code == "scope" and not overview["total"]
    ]


def candidate_metrics(
    item: Candidate, total: int, source: dict[str, Any]
) -> dict[str, Any]:
    denominator = total
    if item.code == "pending_review" and item.kind == "data_gap":
        denominator = source["total_record_count"]
    if item.code == "text_quality" and item.kind == "data_gap":
        denominator = source["text_quality"].get("checked_record_count", 0)
    return {
        "matched_return_samples": item.signal_count,
        "scoped_return_samples": denominator,
        "return_sample_share": percentage(item.signal_count, denominator),
        "trend_direction": "insufficient",
    }
