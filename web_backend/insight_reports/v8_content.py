from __future__ import annotations

import json
import re
from typing import Any

from web_backend.insight_report_contracts import ThemeInsightReportContent
from web_backend.insight_reports.content_common import _items_by_id
from web_backend.insight_reports.v8_text_signals import EARLY_FAILURE

_FIELD_GUIDANCE = {
    "diagnosis": "综合至少两项本主题证据，解释信号之间的关系",
    "hypothesis": "提出能用对照验证的假设，并写明出现什么结果时不成立",
    "impact": "结合本主题证据，解释可能受影响的使用体验或购买环节",
    "action": "说明验证对象和对照方法，并引用本主题证据定位对象",
    "metric": "说明相同范围和筛选口径下的分子、分母，并引用本主题证据",
}
_EMPTY_EXPLANATION = re.compile(
    r"值得核对|可能有差异|持续关注|值得关注|进一步关注|还需观察"
)
_FIELD_REQUIREMENTS = {
    "hypothesis": (
        r"若|如果|假设",
        r"对照|比较|分组|控制|检验",
        r"不成立|证伪|推翻|否定|不支持|才支持",
    ),
    "action": (r"对照|比较|对比|对标",),
    "metric": (r"分子", r"分母"),
}
_REFERENCE = re.compile(r"\[\[([\w.]+)\]\]")
_UNVERIFIED = re.compile(
    r"\d|[零一二两三四五六七八九十百千万]+(?:条|件|例|倍|周|个月|成|分之|%)"
    r"|百分之|个百分点|退货率|总体发生率|根因是|已证实|已被证实|确定由|\b(?:sku|listing)\b|(?-i:\b[A-Z]{3,}\b)|\[|\]",
    re.I,
)


def theme_messages(evidence: dict[str, Any]) -> list[dict[str, str]]:
    blueprint = evidence["blueprint"]
    allowed = {key for theme in blueprint["themes"] for key in theme["evidence_ids"]}
    return [
        {
            "role": "system",
            "content": (
                "你是用户反馈产品分析师。只按固定主题写解释、可验证假设、产品影响、"
                "行动和验证指标。假设标为待验证。不得新增事实、因果或总体发生率；"
                "数字、日期、商品、SKU仅可通过 [[主题证据ID]] 原样引用。"
                "诊断至少引用两项不同的当前主题证据，其余字段每项至少引用一项。"
                "解释证据之间的关系，避免只罗列或复述。假设须说明证伪条件。"
                "行动须写明验证对象和对照方法。指标须写明同口径分子和分母。"
                "禁止使用‘值得核对’‘可能有差异’‘持续关注’等空话。"
                "数字和范围由服务端展开。只返回 JSON。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "output_schema": {
                        "themes": [{"id": "现有主题ID", **_FIELD_GUIDANCE}]
                    },
                    "fixed_blueprint": blueprint,
                    "catalog": {
                        key: value
                        for key, value in evidence["catalog"].items()
                        if key in allowed
                    },
                },
                ensure_ascii=False,
            ),
        },
    ]


def _verified_text(
    field: str, value: Any, fallback: str, evidence: dict[str, Any]
) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 600:
        return fallback
    prose = _REFERENCE.sub("", value)
    refs = set(_REFERENCE.findall(value))
    if (
        len(refs) < (2 if field == "diagnosis" else 1)
        or not refs <= evidence.keys()
        or not re.search(r"[A-Za-z\u4e00-\u9fff]", prose)
        or _UNVERIFIED.search(prose)
        or _EMPTY_EXPLANATION.search(prose)
        or any(
            not re.search(rule, prose) for rule in _FIELD_REQUIREMENTS.get(field, ())
        )
    ):
        return fallback
    return _REFERENCE.sub(lambda match: str(evidence[match[1]]["value"]), value).strip()


def _fallbacks(theme: dict[str, Any], evidence: dict[str, Any]) -> dict[str, str]:
    name, prefix = theme["name"], theme["id"]
    by_label = {item["label"]: item["value"] for item in evidence.values()}
    priorities = (
        "尺码双向分化",
        EARLY_FAILURE,
        "正向价值与质量负向共现",
        "子标签结构",
    )
    signal = next((label for label in priorities if label in by_label), "主题规模")
    return {
        "diagnosis": evidence[f"{prefix}.polarity"]["value"] + by_label[signal],
        "hypothesis": f"若按相同使用条件对照后，{name}的信号差异消失，原先的集中假设不成立。",
        "impact": f"评估{name}时，将命中「{signal}」的使用或购买环节纳入产品验证。",
        "action": (
            f"围绕{name}，选取「{signal}」相关反馈，与同时间范围及同品类的"
            "未命中反馈作对照，逐项复核信号。"
        ),
        "metric": f"分子为命中{name}信号的反馈数，分母为同时间范围、同品类筛选下的反馈总数。",
    }


def assemble_theme_content(
    evidence: dict[str, Any], payload: Any
) -> ThemeInsightReportContent:
    if not isinstance(payload, dict):
        raise ValueError("模型返回的主题说明不是 JSON 对象")
    blueprint = evidence["blueprint"]
    model = _items_by_id(payload.get("themes"))
    themes = []
    for theme in blueprint["themes"]:
        allowed = {key: evidence["catalog"][key] for key in theme["evidence_ids"]}
        writing = model.get(theme["id"], {})
        themes.append(
            {
                **theme,
                **{
                    field: _verified_text(field, writing.get(field), fallback, allowed)
                    for field, fallback in _fallbacks(theme, allowed).items()
                },
            }
        )
    return ThemeInsightReportContent.model_validate({**blueprint, "themes": themes})


def evaluate_theme_quality(
    content: dict[str, Any], evidence: dict[str, Any], text_quality: dict[str, Any]
) -> dict[str, Any]:
    # 目录只保存结构化统计。更新文本质量提示时保留仍适用的主题解释。
    source = {**evidence["source"], "text_quality": text_quality}
    boundaries = evidence["blueprint"]["boundaries"]
    notes = boundaries[:4]
    if note := text_quality.get("note"):
        notes.append(str(note))
    warning = (
        source["quality_issue_codes"] or text_quality.get("status") == "needs_review"
    )
    return {
        "content": {**content, "boundaries": notes},
        "evidence": {**evidence, "source": source},
        "quality_gate": {
            "status": "warning" if warning else "passed",
            "text_quality": text_quality,
        },
    }
