from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from web_backend.common import json_value
from web_backend.dashboard_insight_scope import InsightQueryScope
from web_backend.insight_report_profiles import InsightReportProfile
from web_backend.insight_reports.diagnostic_text import _has_text_anomaly
from web_backend.insight_reports.v8_text_signals import (
    EARLY_FAILURE,
    collect_text_signals,
)
from web_backend.insight_reports.v10_records import keep_examples

_SIZE = re.compile(
    r"(?:^|[-_\s])((?:US|EU)?\d{1,2}(?:\.5)?|XXXL|XXL|XL|XS|S|M|L)$", re.I
)
_SIZE_RANGE = re.compile(
    r"(?:^|[-_\s])((?:US|EU)?)(\d{1,2}(?:\.5)?)\s*[-–~至]\s*(?:US|EU)?(\d{1,2}(?:\.5)?)$",
    re.I,
)

CORE_VALUE_THEME = "产品核心价值"
_GRIP_CODES = {"FUNCTION_GRIP", "FUNCTION_GRIP_U1"}


@dataclass
class _Topic:
    count: int = 0
    positive: int = 0
    negative: int = 0
    mixed: int = 0
    negative_with_other_positive: int = 0
    positive_with_quality_negative: int = 0
    labels: Counter[tuple[str, str]] = field(default_factory=Counter)
    positive_months: Counter[str] = field(default_factory=Counter)
    negative_months: Counter[str] = field(default_factory=Counter)
    text_signals: Counter[str] = field(default_factory=Counter)
    locations: Counter[tuple[str, ...]] = field(default_factory=Counter)
    opposed_pairs: Counter[str] = field(default_factory=Counter)


@dataclass(frozen=True)
class _Feedback:
    month: str
    locations: list[tuple[str, ...]]
    text_signals: set[str]
    positive_themes: set[str]
    has_quality_negative: bool


def _scoped_feedback(scope: InsightQueryScope):
    return scope.connection.execute(
        f"""
        WITH scoped_units AS MATERIALIZED (
            SELECT DISTINCT r.result_version_id, r.classification_key
            FROM {scope.records_table} r WHERE {scope.where_sql}
        ), labels AS (
            SELECT l.result_version_id, l.classification_key,
                   json_group_array(json_array(l.label_code, l.label_name,
                       aligned_group(l.label_group, l.label_code, l.result_version_id),
                       CASE l.label_kind WHEN 'positive' THEN 'POSITIVE' ELSE 'NEGATIVE' END)
                   ) AS entries
            FROM scoped_units s JOIN classification_unit_labels l
              USING(result_version_id, classification_key)
            WHERE l.label_kind IN ('problem', 'positive')
            GROUP BY l.result_version_id, l.classification_key
        )
        SELECT r.return_date, r.listing, r.product_name, r.product_sku,
               raw.product_match_status, u.comment, u.classification_json, labels.entries, raw.*
        FROM {scope.records_table} r
        JOIN classification_result_records raw ON raw.id = r.id
        LEFT JOIN classification_units u USING(result_version_id, classification_key)
        LEFT JOIN labels USING(result_version_id, classification_key)
        WHERE {scope.where_sql}
        ORDER BY raw.id
        """,
        (*scope.params, *scope.params),
    )


def _theme_key(code: str, group: str, profile: InsightReportProfile) -> str:
    if profile.key == "footwear" and code in _GRIP_CODES:
        return "防滑与抓地"
    if group == "整体反馈与信息不足":
        return "使用场景与购买意愿"
    return group or "其他反馈"


def _feedback_themes(row, taxonomy, profile):
    themes: dict[str, dict[tuple[str, str], set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    indexed = json_value(row["entries"], [])
    labels = {code: (name or code, group) for code, name, group, _ in indexed}
    for code, name, group, tone in indexed:
        themes[_theme_key(code, group, profile)][(code, name or code)].add(tone)
    for fact in json_value(row["classification_json"], {}).get("semantic_units", []):
        code = fact.get("label_code")
        if code:
            name, group = labels.get(code) or taxonomy.get(code) or (code, "")
            themes[_theme_key(code, group, profile)][(code, name)].add(
                fact.get("sentiment")
            )
    return themes


def _feedback_locations(row) -> list[tuple[str, ...]]:
    locations: list[tuple[str, ...]] = []
    listing = row["listing"]
    if listing:
        locations.append(("Listing", listing))
    if row["product_match_status"] != "matched" or not row["product_name"]:
        return locations
    product = row["product_name"]
    locations.append(("商品", product, listing or ""))
    sku = row["product_sku"]
    if sku:
        locations.append(("SKU", sku, product, listing or ""))
        if band := _sku_size_band(sku):
            locations.append(("尺码段", band, product, listing or ""))
    return locations


def _sku_size_band(sku: str) -> str:
    if (explicit := _SIZE_RANGE.search(sku)) and 0 < float(explicit[3]) - float(
        explicit[2]
    ) <= 4:
        return f"{explicit[1].upper()}{explicit[2]}–{explicit[3]}"
    if size := _SIZE.search(sku):
        return _size_band(size[1].upper())
    return ""


def _size_band(suffix: str) -> str:
    if suffix in {"XS", "S", "M", "L", "XL", "XXL", "XXXL"}:
        return {"XS": "XS–S", "S": "XS–S", "M": "M–L", "L": "M–L"}.get(
            suffix, "XL–XXXL"
        )
    system = suffix[:2] if suffix[:2] in {"US", "EU"} else ""
    number = float(suffix[len(system) :])
    step = 2 if system == "US" or number < 20 else 4
    start = int(number // step) * step
    return f"{system}{start}–<{start + step}"


def _add_theme_feedback(
    topic: _Topic,
    theme: str,
    members: dict[tuple[str, str], set[str]],
    feedback: _Feedback,
    profile: InsightReportProfile,
) -> None:
    topic.count += 1
    tones = set().union(*members.values())
    topic.positive += "POSITIVE" in tones
    topic.negative += "NEGATIVE" in tones
    topic.mixed += {"POSITIVE", "NEGATIVE"}.issubset(tones)
    topic.negative_with_other_positive += "NEGATIVE" in tones and bool(
        feedback.positive_themes - {theme}
    )
    topic.labels.update(members.keys())
    topic.locations.update(feedback.locations)
    if feedback.month:
        topic.positive_months[feedback.month] += "POSITIVE" in tones
        topic.negative_months[feedback.month] += "NEGATIVE" in tones
    topic.text_signals.update(
        signal
        for signal in feedback.text_signals
        if signal != EARLY_FAILURE or _contains_quality_negative(theme, members)
    )
    codes = {code for code, _ in members}
    for left, right in profile.polarization_pairs:
        a, b = bool(codes.intersection(left)), bool(codes.intersection(right))
        topic.opposed_pairs["left"] += a
        topic.opposed_pairs["right"] += b
        topic.opposed_pairs["overlap"] += a and b


def _add_core_value(
    topic: _Topic,
    themes: dict[str, dict[tuple[str, str], set[str]]],
    feedback: _Feedback,
) -> None:
    topic.count += 1
    topic.positive += 1
    topic.positive_with_quality_negative += feedback.has_quality_negative
    topic.labels.update(
        {
            label
            for members in themes.values()
            for label, tones in members.items()
            if "POSITIVE" in tones
        }
    )
    if feedback.month:
        topic.positive_months[feedback.month] += 1
    topic.locations.update(feedback.locations)
    topic.text_signals.update(feedback.text_signals - {EARLY_FAILURE})


def _contains_quality_negative(
    theme: str, members: dict[tuple[str, str], set[str]]
) -> bool:
    return any(
        "NEGATIVE" in tones
        and (
            "质量" in theme
            or "耐用" in theme
            or code.startswith(("QUALITY_", "DURABILITY_"))
        )
        for (code, _), tones in members.items()
    )


def collect_report_themes(
    scope: InsightQueryScope, labels: list[Any], profile: InsightReportProfile
) -> dict[str, Any]:
    taxonomy = {label.code: (label.name, label.group) for label in labels}
    themes: dict[str, _Topic] = defaultdict(_Topic)
    overview: Counter[str] = Counter()
    months: Counter[str] = Counter()
    locations: Counter[tuple[str, ...]] = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _scoped_feedback(scope):
        per_theme = _feedback_themes(row, taxonomy, profile)
        month = (row["return_date"] or "")[:7]
        place = _feedback_locations(row)
        text = row["comment"] or ""
        valid_text = bool(text.strip()) and not _has_text_anomaly(text)
        signals = collect_text_signals(text) if valid_text else set()
        feedback = _Feedback(
            month,
            place,
            signals,
            {
                theme
                for theme, members in per_theme.items()
                if any("POSITIVE" in tones for tones in members.values())
            },
            any(
                _contains_quality_negative(theme, members)
                for theme, members in per_theme.items()
            ),
        )
        overview["total"] += 1
        overview["labeled"] += bool(per_theme)
        overview["text"] += bool(text.strip())
        overview["mapped"] += row["product_match_status"] == "matched" and bool(
            row["product_name"]
        )
        if month:
            months[month] += 1
        locations.update(place)
        for theme, members in per_theme.items():
            _add_theme_feedback(themes[theme], theme, members, feedback, profile)
            if valid_text:
                keep_examples(
                    examples,
                    theme,
                    members,
                    row,
                    text,
                    EARLY_FAILURE in signals
                    and _contains_quality_negative(theme, members),
                    profile.polarization_pairs,
                )
        if feedback.positive_themes:
            _add_core_value(themes[CORE_VALUE_THEME], per_theme, feedback)
    return {
        "overview": overview,
        "topics": themes,
        "months": months,
        "locations": locations,
        "examples": examples,
    }
