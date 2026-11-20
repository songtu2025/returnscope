from __future__ import annotations

from typing import Any

from web_backend.insight_reports.v8_statistics import CORE_VALUE_THEME, _Topic
from web_backend.insight_reports.v8_text_signals import EARLY_FAILURE

QUALITY_THEME = "质量与耐用"


def size_split_count(topic: _Topic) -> int:
    left, right = topic.opposed_pairs["left"], topic.opposed_pairs["right"]
    return left + right - topic.opposed_pairs["overlap"] if left and right else 0


def theme_title(name: str, topic: _Topic) -> str:
    if name == CORE_VALUE_THEME:
        return f"{topic.count}条反馈肯定了产品核心价值"
    if size_count := size_split_count(topic):
        return f"尺码呈双向分化，涉及{size_count}条反馈"
    if name == QUALITY_THEME and topic.negative:
        title = f"耐用性收到{topic.negative}条负向反馈"
        if early := topic.text_signals[EARLY_FAILURE]:
            title += f"，其中{early}条提及首用或短期失效"
        return title
    if name in {"使用感受", "功能表现"} and topic.negative:
        return f"{name}涉及{topic.negative}条负向反馈"
    return f"{name}涉及{topic.count}条反馈"


def management_summary(
    themes: list[dict[str, Any]], topics: dict[str, _Topic], catalog: dict[str, Any]
) -> list[dict[str, Any]]:
    highest_negative = max((topic.negative for topic in topics.values()), default=0)
    return [
        _summary_item(theme, topics[theme["name"]], catalog, highest_negative)
        for theme in themes[:3]
    ]


def _summary_item(
    theme: dict[str, Any], topic: _Topic, catalog: dict[str, Any], highest_negative: int
) -> dict[str, Any]:
    name, prefix = theme["name"], theme["id"]
    polarity_id = f"{prefix}.polarity"
    if name == CORE_VALUE_THEME:
        statement = f"{topic.count} 条反馈肯定了产品价值。"
        ids = [f"{prefix}.volume"]
        if topic.positive_with_quality_negative:
            ids.append(f"{prefix}.quality_overlap")
            statement += catalog[ids[-1]]["value"]
        return _summary("核心价值获得正向反馈", statement, ids)
    if name == QUALITY_THEME and topic.negative:
        return _quality_summary(topic, catalog, prefix, highest_negative)
    split_id = f"{prefix}.polarization"
    if split_id in catalog:
        return _summary("尺码呈双向分化", catalog[split_id]["value"], [split_id])
    return _summary(theme["title"], catalog[polarity_id]["value"], [polarity_id])


def _quality_summary(
    topic: _Topic, catalog: dict[str, Any], prefix: str, highest_negative: int
) -> dict[str, Any]:
    ids = [f"{prefix}.polarity"]
    title = (
        "耐用性是首要风险" if topic.negative == highest_negative else "耐用性是主要风险"
    )
    statement = f"耐用性收到 {topic.negative} 条负向反馈"
    if early := topic.text_signals[EARLY_FAILURE]:
        ids.extend(
            key
            for key, item in catalog.items()
            if key.startswith(f"{prefix}.") and item["label"] == EARLY_FAILURE
        )
        statement += f"，其中 {early} 条提及首用或短期失效"
    statement += "。"
    labels_id = f"{prefix}.labels"
    if labels_id in catalog:
        ids.append(labels_id)
        labels = [item["name"] for item in catalog[labels_id]["data"][:3]]
        statement += f"主要子标签为{'、'.join(labels)}。"
    return _summary(title, statement, ids)


def _summary(title: str, statement: str, evidence_ids: list[str]) -> dict[str, Any]:
    return {"title": title, "statement": statement, "evidence_ids": evidence_ids}


def visible_theme_facts(name: str, facts: dict[str, tuple[str, str, Any]]) -> list[str]:
    chosen = ["volume"]
    preferred = (
        ("quality_overlap", "labels")
        if name == CORE_VALUE_THEME
        else (
            "polarization",
            "polarity",
            "labels",
        )
    )
    chosen.extend(key for key in preferred if key in facts)
    text = sorted(
        (
            key
            for key, (label, _value, data) in facts.items()
            if key.startswith("text")
            and data["count"] >= (3 if label == EARLY_FAILURE else 5)
        ),
        key=lambda key: (
            _text_priority(name, facts[key][0]),
            -facts[key][2]["count"],
            key,
        ),
    )
    chosen.extend(text[:2] if name == CORE_VALUE_THEME else text[:1])
    if "trend" in facts:
        chosen.append("trend")
    nearby = [
        key
        for key in ("listing", "product", "sku", "size")
        if key in facts and facts[key][2]["lift"] > 1
    ]
    if nearby:
        chosen.append(max(nearby, key=lambda key: facts[key][2]["lift"]))
    return [facts[key][1] for key in chosen[:6]]


def _text_priority(name: str, label: str) -> int:
    if name == "防滑与抓地" and label == "湿滑地面场景":
        return 0
    if label == EARLY_FAILURE:
        return 0
    if label.startswith("明确"):
        return 1
    if label in {"湿滑地面场景", "涉水场景"}:
        return 2
    return 3
