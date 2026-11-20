from __future__ import annotations

from typing import Any

from web_backend.dashboard_support import percentage
from web_backend.insight_reports.v7_candidates import MIN_SAMPLES
from web_backend.insight_reports.v8_evidence import _locations
from web_backend.insight_reports.v8_statistics import _Topic


def _metric(label: str, count: int, total: int, scope: str) -> dict[str, Any]:
    return {
        "label": label,
        "numerator": count,
        "denominator": total,
        "unit": "条",
        "percent": percentage(count, total) if total else None,
        "scope": scope,
    }


def _timeline(quality: _Topic, stats: dict[str, Any]) -> list[dict[str, Any]]:
    months = stats["months"]
    reliable = sorted(month for month in months if months[month] >= MIN_SAMPLES)
    if not reliable or not quality.negative:
        return []
    peak = max(
        reliable, key=lambda month: quality.negative_months[month] / months[month]
    )
    window = reliable[max(0, reliable.index(peak) - 4) : reliable.index(peak) + 1]
    periods = [[peak]]
    ordinal = [int(month[:4]) * 12 + int(month[5:]) for month in window]
    if len(window) == 5 and ordinal == list(range(ordinal[0], ordinal[0] + 5)):
        periods = [window[:2], window[2:], [peak]]
    return [
        _metric(
            group[0] if len(group) == 1 else f"{group[0]} 至 {group[-1]}",
            sum(quality.negative_months[month] for month in group),
            sum(months[month] for month in group),
            "质量负向 / 同期纳入反馈",
        )
        for group in periods
    ]


def _small_label(size: _Topic) -> int:
    return max(
        (
            count
            for (code, _), count in size.labels.items()
            if code in {"FIT_TOO_SMALL", "FIT_TOO_SMALL_U1"}
        ),
        default=0,
    )


def _label_rows(topic: _Topic, total: int, scope: str) -> list[dict[str, Any]]:
    return [
        _metric(name, count, total, scope)
        for (_, name), count in sorted(
            topic.labels.items(), key=lambda item: (-item[1], item[0])
        )[:5]
    ]


def _experience_rows(
    core: _Topic, experience: _Topic, total: int
) -> list[dict[str, Any]]:
    rows = _label_rows(core, total, "纳入反馈")
    rows += [
        _metric(label, count, experience.count, "使用感受主题反馈")
        for label, count in (
            ("使用感受正向", experience.positive),
            ("使用感受负向", experience.negative),
            ("使用感受正负共存", experience.mixed),
        )
    ]
    rows += [
        _metric(
            "肯定价值且报告质量问题",
            core.positive_with_quality_negative,
            core.positive,
            "肯定核心价值的反馈",
        )
    ]
    rows += [
        _metric(name, count, experience.count, "使用感受主题反馈")
        for (_, name), count in sorted(experience.labels.items())
        if "鞋垫移位" in name
    ]
    return rows


def _quality_location(quality: _Topic, stats: dict[str, Any]) -> list[dict[str, Any]]:
    product = _locations(quality, stats["locations"]).get("product")
    if not product:
        return []
    _, _, data = product
    places = [place for place in stats["locations"] if place[0] == "商品"]
    return [
        _metric(
            f"{data['location'][1]} · 质量主题",
            data["count"],
            data["total"],
            "该商品的匹配反馈",
        ),
        _metric(
            "商品基线 · 质量主题",
            sum(quality.locations[place] for place in places),
            sum(stats["locations"][place] for place in places),
            "所有匹配商品反馈",
        ),
    ]


def _coverage(
    evidence: dict[str, Any], stats: dict[str, Any], total: int, mapped: int
) -> list[dict[str, Any]]:
    rows = [
        _metric("商品已匹配", mapped, total, "纳入反馈"),
        _metric("缺少商品映射", total - mapped, total, "纳入反馈"),
        _metric(
            "来源待复核",
            evidence["source"]["pending_review_record_count"],
            total,
            "纳入反馈",
        ),
    ]
    for kind in ("Listing", "商品"):
        leading = min(
            (
                (count, place[1])
                for place, count in stats["locations"].items()
                if place[0] == kind
            ),
            key=lambda item: (-item[0], item[1]),
            default=(0, ""),
        )
        if leading[0] >= MIN_SAMPLES:
            rows.append(
                _metric(f"{kind} {leading[1]} 样本集中", leading[0], total, "纳入反馈")
            )
    return rows
