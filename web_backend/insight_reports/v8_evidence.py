from __future__ import annotations

from typing import Any

from web_backend.dashboard_support import percentage
from web_backend.insight_report_diagnostics import _product_mapping_check
from web_backend.insight_report_evidence import _build_source
from web_backend.insight_report_profiles import resolve_insight_report_profile
from web_backend.insight_reports.evidence_catalog import _scope_catalog
from web_backend.insight_reports.v7_candidates import MIN_SAMPLES
from web_backend.insight_reports.v8_statistics import CORE_VALUE_THEME, _Topic
from web_backend.insight_reports.v8_summary import (
    management_summary,
    size_split_count,
    theme_title,
    visible_theme_facts,
)

_FOOTWEAR_TOPICS = ("质量与耐用", "尺码与适配", "防滑与抓地")


def build_theme_evidence(analysis: dict[str, Any]) -> dict[str, Any]:
    if analysis.get("hierarchy_conflict"):
        raise ValueError(analysis["message"])
    profile = resolve_insight_report_profile(analysis["sources"])
    mapping = _product_mapping_check(
        analysis["summary"], analysis["filter_options"].get("listings", [])
    )
    source = _build_source(analysis, mapping, profile)
    stats = analysis["report_themes"]
    overview = stats["overview"]
    total = overview["total"]
    source["included_record_count"] = total
    source["label_coverage"] = percentage(overview["labeled"], total)
    catalog = _scope_catalog(analysis, mapping, profile)
    names = _important_topics(stats["topics"], profile.key)
    themes = [
        _build_theme(name, stats["topics"][name], stats, catalog, index)
        for index, name in enumerate(names, 1)
    ]
    summary = management_summary(themes, stats["topics"], catalog)
    boundaries = _data_boundaries(source, overview)
    return {
        "source": source,
        "catalog": catalog,
        "analysis": {
            "summary": analysis["summary"],
            "review_bias": analysis["review_bias"],
        },
        "blueprint": {
            "report_type": "theme_insight",
            "title": _report_title({name: stats["topics"][name] for name in names}),
            "executive_summary": summary,
            "themes": themes,
            "boundaries": boundaries,
        },
    }


def _important_topics(topics: dict[str, _Topic], profile: str) -> list[str]:
    primary = [CORE_VALUE_THEME] if CORE_VALUE_THEME in topics else []
    if profile == "footwear":
        primary.extend(name for name in _FOOTWEAR_TOPICS if name in topics)
    other = sorted(
        (
            name
            for name, topic in topics.items()
            if name not in primary and (topic.negative or not topic.positive)
        ),
        key=lambda name: (-topics[name].count, name),
    )
    return (primary + other)[: 5 if profile == "footwear" else 6]


def _report_title(topics: dict[str, _Topic]) -> str:
    if not topics:
        return "当前反馈缺少可用于主题分析的分类信号"
    strength = min(topics, key=lambda name: (-topics[name].positive, name))
    risk = min(topics, key=lambda name: (-topics[name].negative, name))
    if strength != risk and topics[strength].positive and topics[risk].negative:
        return f"{strength}是主要正向信号，{risk}是主要负向信号"
    return f"当前反馈的重点覆盖{'、'.join(list(topics)[:3])}"


def _build_theme(
    name: str, topic: _Topic, stats: dict[str, Any], catalog: dict[str, Any], index: int
) -> dict[str, Any]:
    total = stats["overview"]["total"]
    prefix = f"theme.{index}"
    size = f"{topic.count} / {total} 条反馈涉及{name}，样本占比 {percentage(topic.count, total):.1f}%。"
    facts = {
        "volume": ("主题规模", size, {"count": topic.count, "scope": total}),
        "polarity": (
            "评价方向",
            f"正向 {topic.positive} 条、负向 {topic.negative} 条，同一反馈中正负并存 {topic.mixed} 条。",
            {
                "positive": topic.positive,
                "negative": topic.negative,
                "mixed": topic.mixed,
            },
        ),
    }
    if topic.positive_with_quality_negative:
        count = topic.positive_with_quality_negative
        facts["quality_overlap"] = (
            "正向价值与质量负向共现",
            f"{count} 条肯定产品价值的反馈同时报告了质量问题。",
            {"count": count},
        )
    if topic.negative_with_other_positive:
        count = topic.negative_with_other_positive
        facts["cooccurrence"] = (
            "跨主题正负共现",
            f"{count} 条本主题的负向反馈同时对其他主题表达正面评价。",
            {"count": count},
        )
    facts.update(_structure(topic))
    facts.update(_trend(topic, stats["months"]))
    facts.update(_text_observations(topic))
    facts.update(_locations(topic, stats["locations"]))
    for key, (label, value, data) in facts.items():
        catalog[f"{prefix}.{key}"] = {"label": label, "value": value, "data": data}
    return {
        "id": prefix,
        "name": name,
        "title": theme_title(name, topic),
        "priority": "P0"
        if topic.negative >= 10 and topic.negative >= topic.positive
        else "P1",
        "facts": visible_theme_facts(name, facts),
        "evidence_ids": [f"{prefix}.{key}" for key in facts],
    }


def _structure(topic: _Topic) -> dict[str, Any]:
    labels = sorted(topic.labels.items(), key=lambda item: (-item[1], item[0]))[:6]
    values = [
        {"code": code, "name": label, "count": count} for (code, label), count in labels
    ]
    facts: dict[str, Any] = {}
    if values:
        facts["labels"] = (
            "子标签结构",
            "；".join(f"{item['name']} {item['count']} 条" for item in values)
            + "。同一反馈可有多个子标签。",
            values,
        )
    left, right = topic.opposed_pairs["left"], topic.opposed_pairs["right"]
    if split_count := size_split_count(topic):
        overlap = topic.opposed_pairs["overlap"]
        facts["polarization"] = (
            "尺码双向分化",
            f"偏小 {left} 条、偏大 {right} 条，重叠 {overlap} 条，共涉及 {split_count} 条去重反馈。",
            dict(topic.opposed_pairs),
        )
    return facts


def _trend(topic: _Topic, months: dict[str, int]) -> dict[str, Any]:
    if len(months) < 2 or not (topic.negative or topic.positive):
        return {}
    counts = topic.negative_months if topic.negative else topic.positive_months
    direction = "负向" if topic.negative else "正向"
    series: list[dict[str, Any]] = [
        {
            "month": month,
            "count": counts[month],
            "total": months[month],
            "share": percentage(counts[month], months[month]),
        }
        for month in sorted(months)
    ]
    reliable = [item for item in series if item["total"] >= MIN_SAMPLES]
    if len(reliable) < 2:
        return {"trend": (f"各月{direction}样本占比", "可比月份样本量有限。", series)}
    peak = max(reliable, key=lambda item: item["share"])
    value = (
        f"{direction}样本占比在 {peak['month']} 达到可比月份峰值 "
        f"{peak['share']:.1f}%（{peak['count']}/{peak['total']}）。"
    )
    value += _peak_phase_comparison(reliable, peak)
    shares = [item["share"] for item in reliable]
    changes = [right - left for left, right in zip(shares, shares[1:], strict=False)]
    if any(change > 0 for change in changes) and any(change < 0 for change in changes):
        value += "样本占比有升有降。"
    return {"trend": (f"各月{direction}样本占比", value, series)}


def _peak_phase_comparison(reliable: list[dict[str, Any]], peak: dict[str, Any]) -> str:
    index = reliable.index(peak)
    if index < 4:
        return ""
    window = reliable[index - 4 : index + 1]
    try:
        month_numbers = [
            int(item["month"][:4]) * 12 + int(item["month"][5:]) for item in window
        ]
    except ValueError:
        return ""
    if month_numbers != list(range(month_numbers[0], month_numbers[0] + 5)):
        return ""
    phases = []
    for phase in (window[:2], window[2:]):
        count = sum(item["count"] for item in phase)
        total = sum(item["total"] for item in phase)
        phases.append(
            f"{phase[0]['month']} 至 {phase[-1]['month']} "
            f"为 {percentage(count, total):.1f}%（{count}/{total}）"
        )
    return "，".join(phases) + "。"


def _locations(topic: _Topic, totals: dict[tuple[str, ...], int]) -> dict[str, Any]:
    results = {}
    for dimension in ("Listing", "商品", "SKU", "尺码段"):
        options = [
            (place, count)
            for place, count in topic.locations.items()
            if place[0] == dimension and count >= 3 and totals[place] >= MIN_SAMPLES
        ]
        if not options:
            continue
        available = sum(value for key, value in totals.items() if key[0] == dimension)
        matched = sum(
            value for key, value in topic.locations.items() if key[0] == dimension
        )
        base_rate = matched / available
        place, count = min(
            options,
            key=lambda item: (
                -(item[1] - totals[item[0]] * base_rate),
                -item[1],
                item[0],
            ),
        )
        denominator = totals[place]
        share, baseline = percentage(count, denominator), percentage(matched, available)
        key = {
            "Listing": "listing",
            "商品": "product",
            "SKU": "sku",
            "尺码段": "size",
        }[dimension]
        label = " / ".join(value for value in place[1:] if value)
        lift = round(count / denominator / base_rate, 2)
        results[key] = (
            f"{dimension}反馈分布",
            f"{label}：{count}/{denominator} 条，样本内占比 {share:.1f}%，"
            f"同维度基线 {baseline:.1f}%，为基线的 {lift:.2f} 倍。",
            {"location": place, "count": count, "total": denominator, "lift": lift},
        )
    return results


def _text_observations(topic: _Topic) -> dict[str, Any]:
    return {
        f"text{index}": (
            name,
            f"{name}相关表达命中 {count} 条主题反馈。",
            {"count": count},
        )
        for index, (name, count) in enumerate(sorted(topic.text_signals.items()), 1)
    }


def _data_boundaries(source: dict[str, Any], overview: dict[str, int]) -> list[str]:
    total = overview["total"]
    items = [
        f"纳入 {total} 条反馈，{overview['labeled']} 条有标签，{overview['text']} 条有文本。",
        f"{source['pending_review_record_count']} 条来源反馈待复核，"
        f"{overview['mapped']} / {total} 条反馈具有可靠商品映射。",
        "商品、SKU 和尺码段只分析已匹配反馈；尺码段按 SKU 尾码分组，需核对实际尺码。",
        "主题可重叠，文本规则只记录明确表述的线索。占比描述当前反馈样本。",
    ]
    if note := source["text_quality"].get("note"):
        items.append(str(note))
    return items
