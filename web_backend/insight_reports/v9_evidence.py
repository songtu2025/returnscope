from __future__ import annotations

from typing import Any

from web_backend.dashboard_support import percentage
from web_backend.insight_reports.v8_statistics import CORE_VALUE_THEME, _Topic
from web_backend.insight_reports.v8_summary import (
    EARLY_FAILURE,
    QUALITY_THEME,
    size_split_count,
)

_SIZING = "尺码与适配"
_GRIP = "防滑与抓地"
_MEANINGS = {
    CORE_VALUE_THEME: "保留舒适、合脚等已获认可的设计要素，改款时与原款做体验对照。",
    QUALITY_THEME: "先复验撕裂、开裂与散架的发生条件，区分首用失效和长期磨损。",
    _SIZING: "按同款同码对照偏小和偏大反馈，分别验证脚长、脚宽和尺码说明。",
    _GRIP: "把湿滑与干燥条件分开验证，再决定页面能承诺哪些使用场景。",
}
_ACTIONS = {
    QUALITY_THEME: (
        "P0",
        "先验证材料与连接处的短期失效",
        "用同款样品对照复现撕裂、开裂和散架，记录首次出现时间与受损位置。",
    ),
    _SIZING: (
        "P1",
        "分开排查偏小和偏大",
        "用同款同码样品对照脚长和脚宽，核对产品尺寸与尺码说明。",
    ),
    CORE_VALUE_THEME: (
        "P1",
        "保住已获认可的体验",
        "对照改款与原款的舒适度、贴合和使用条件，避免修复风险时削弱优点。",
    ),
    _GRIP: (
        "P1",
        "验证防滑卖点适用的场景",
        "按湿滑与干燥条件对照测试，确定可写进产品页面的适用范围。",
    ),
}


def prepare_concise_evidence(
    evidence: dict[str, Any], stats: dict[str, Any]
) -> dict[str, Any]:
    blueprint = evidence["blueprint"]
    catalog = evidence["catalog"]
    themes = blueprint["themes"]
    names = {theme["name"] for theme in themes}
    topics = stats["topics"]
    insights = [
        _build_insight(
            theme, topics[theme["name"]], catalog, stats["overview"]["total"]
        )
        for theme in themes
        if theme["name"] != "使用感受" or len(themes) <= 4
    ]
    if trend := _time_insight(themes, catalog):
        insights.append(trend)
    if themes:
        insights.append(_coverage_insight(evidence, stats))
    actions = [
        {
            "id": item["id"],
            "priority": priority,
            "title": title,
            "action": fallback,
            "evidence_ids": item["evidence_ids"],
        }
        for name, (priority, title, fallback) in _ACTIONS.items()
        for item in insights
        if item["name"] == name and (priority != "P0" or topics[name].negative)
    ]
    title, judgment, closing = _product_judgment(names, topics)
    blueprint["concise"] = {
        "report_type": "concise_insight",
        "title": title,
        "judgment": judgment,
        "insights": insights[:7],
        "actions": actions,
        "closing": closing,
        "boundaries": _brief_boundaries(blueprint["boundaries"], names),
    }
    return evidence


def _product_judgment(
    names: set[str], topics: dict[str, _Topic]
) -> tuple[str, str, str]:
    if (
        {CORE_VALUE_THEME, QUALITY_THEME, _SIZING} <= names
        and topics[QUALITY_THEME].negative
        and size_split_count(topics[_SIZING])
    ):
        return (
            "舒适和合脚已获认可，耐用性应先改进，尺码问题须分方向处理",
            "改款应保留舒适与合脚的体验，先复现短期失效，再区分偏小和偏大的原因。",
            "耐用性决定改款顺序，双向尺码问题需要分别验证，防滑卖点以场景测试为准。",
        )
    if QUALITY_THEME in names and topics[QUALITY_THEME].negative:
        return (
            "先解决耐用性风险，再扩展产品卖点",
            "优先复验失效表现，同时验证改款能否保住已获认可的体验。",
            "产品调整以可复现的失效和体验差异为依据。",
        )
    if not names:
        phrase = "当前反馈缺少可定位的产品判断"
        return phrase, "先补齐反馈分类证据。", "补足证据后再确定产品优先级。"
    return (
        "保留已有体验优势，优先验证影响使用的差异",
        "把已获认可的表现作为改款对照，把反复出现的问题放入验证计划。",
        "以用户能稳定获得的体验决定产品取舍。",
    )


def _build_insight(
    theme: dict[str, Any], topic: _Topic, catalog: dict[str, Any], total: int
) -> dict[str, Any]:
    name, prefix = theme["name"], theme["id"]
    title, fact = _theme_signal(name, topic, total)
    refs = list(theme["evidence_ids"])
    if name == _SIZING and size_split_count(topic):
        fact = catalog[f"{prefix}.polarization"]["value"]
        for code in ("FIT_TOO_SMALL_U1", "FIT_TOO_SMALL"):
            exact = sum(
                count for (label, _), count in topic.labels.items() if label == code
            )
            if exact:
                ref = f"{prefix}.exact-small"
                text = f"单一「偏小」标签 {exact} 条。"
                catalog[ref] = {
                    "label": "单一偏小标签",
                    "value": text,
                    "data": {"code": code, "count": exact},
                }
                refs.append(ref)
                fact = text + fact.replace("偏小 ", "偏小方向 ", 1).replace(
                    "偏大 ", "偏大方向 ", 1
                )
                break
    return {
        "id": prefix,
        "name": name,
        "title": title,
        "fact": fact,
        "meaning": _MEANINGS.get(name, f"将{name}中的反复反馈作为产品验证线索。"),
        "evidence_ids": refs,
    }


def _theme_signal(name: str, topic: _Topic, total: int) -> tuple[str, str]:
    if name == CORE_VALUE_THEME:
        labels = "、".join(
            f"{label.partition('（')[0]} {count} 条（{percentage(count, total):.1f}%）"
            for (_, label), count in sorted(
                topic.labels.items(), key=lambda entry: (-entry[1], entry[0])
            )[:5]
        )
        return (
            "产品的基础价值值得保留",
            f"{topic.positive} 条反馈肯定产品体验（{percentage(topic.positive, total):.1f}%），前五项为{labels}。",
        )
    if name == QUALITY_THEME and topic.negative:
        early = topic.text_signals[EARLY_FAILURE]
        fact = f"耐用性收到 {topic.negative} 条负向反馈"
        if early:
            fact += f"，其中 {early} 条（{percentage(early, topic.negative):.1f}%）提及首用或短期失效"
        return "耐用性应排在改进首位", fact + "。"
    if name == _SIZING and size_split_count(topic):
        return "尺码适配不稳定，偏小和偏大需要分开处理", ""
    if name == _GRIP:
        fact = f"抓地反馈中 {topic.positive} 条正向、{topic.negative} 条负向。"
        if wet := topic.text_signals["湿滑地面场景"]:
            fact += f"有 {wet} 条提及湿滑地面。"
        return "防滑有卖点潜力，适用场景需要验证", fact
    return (
        f"{name}仍有验证空间",
        f"有关{name}的反馈中有 {topic.negative} 条负向、{topic.positive} 条正向。",
    )


def _time_insight(
    themes: list[dict[str, Any]], catalog: dict[str, Any]
) -> dict[str, Any] | None:
    quality = next((theme for theme in themes if theme["name"] == QUALITY_THEME), None)
    if not quality:
        return None
    ref = f"{quality['id']}.trend"
    trend = catalog.get(ref)
    if (
        not trend
        or trend["label"] != "各月负向样本占比"
        or " 至 " not in trend["value"]
    ):
        return None
    return {
        "id": "time",
        "name": "时间信号",
        "title": "耐用性风险在不同时间阶段表现不一",
        "fact": trend["value"].removesuffix("样本占比有升有降。"),
        "meaning": "按同期样本对照失效表现，核查产品组合、批次或使用场景能否解释差异。",
        "evidence_ids": [ref],
    }


def _coverage_insight(
    evidence: dict[str, Any], stats: dict[str, Any]
) -> dict[str, Any]:
    source = evidence["source"]
    total, mapped = (stats["overview"][key] for key in ("total", "mapped"))
    fact = (
        f"纳入 {total} 条反馈，{source['pending_review_record_count']} 条来源反馈待复核，"
        f"{total - mapped} 条缺少可靠商品映射。"
    )
    refs = ["scope", "product_mapping"]
    for kind, slug, denominator, label in (
        ("Listing", "listing", total, "主要 Listing"),
        ("商品", "product", mapped, "主要匹配商品"),
    ):
        counts = (
            (count, name)
            for (location, name, *_), count in stats["locations"].items()
            if location == kind
        )
        count, name = min(counts, key=lambda item: (-item[0], item[1]), default=(0, ""))
        if count >= 10 and count * 2 >= denominator:
            ref = f"scope.leading-{slug}"
            concentration = f"{label} {name} 有 {count} 条（占全部反馈 {percentage(count, total):.1f}%）。"
            evidence["catalog"][ref] = {
                "label": f"{label} 的样本集中度"
                if kind == "Listing"
                else f"{label}的样本集中度",
                "value": concentration,
                "data": {"name": name, "count": count, "total": total},
            }
            refs.append(ref)
            fact += concentration
    return {
        "id": "coverage",
        "name": "数据代表性",
        "title": "样本足以定位问题，商品结论仍需复核",
        "fact": fact,
        "meaning": "当前反馈支持排定验证顺序，涉及具体商品的判断使用已匹配反馈，并结合复核结果确认。",
        "evidence_ids": refs,
    }


def _brief_boundaries(boundaries: list[str], names: set[str]) -> list[str]:
    notes = [
        *boundaries,
        "看板快照提供反馈记录，未包含销量或订单总量，无法估算总体发生率。",
    ]
    if QUALITY_THEME in names:
        notes.append(
            "短期线索按质量负向反馈中明确的首用、小时、天或短周表述统计。历史简报的计算规则未随工作簿保存，无法逐条核对两次结果的差异。"
        )
    if _SIZING in names:
        notes.append(
            "偏小方向汇总偏小、偏紧窄和偏短；偏大方向汇总偏大、偏松宽和偏长。各方向及并集均按反馈去重。"
        )
    return notes
