from __future__ import annotations

from typing import Any

from web_backend.insight_reports.v8_statistics import CORE_VALUE_THEME, _Topic
from web_backend.insight_reports.v8_text_signals import EARLY_FAILURE
from web_backend.insight_reports.v10_metrics import (
    _coverage,
    _experience_rows,
    _label_rows,
    _metric,
    _quality_location,
    _small_label,
    _timeline,
)


def _chapter(
    key: str,
    name: str,
    title: str,
    metrics: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    boundary: str,
    definition: str,
    explanation: str,
    action: str,
    examples: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "id": key,
        "name": name,
        "title": title,
        "metrics": metrics,
        "breakdown": rows,
        "boundary": boundary,
        "definition": definition,
        "explanation": explanation,
        "action": action,
        "records": examples,
    }


def build_verifiable_report(
    evidence: dict[str, Any], stats: dict[str, Any]
) -> dict[str, Any]:
    topics = stats["topics"]
    examples = stats["examples"]
    total = stats["overview"]["total"]
    mapped = stats["overview"]["mapped"]
    core = topics.get(CORE_VALUE_THEME, _Topic())
    experience = topics.get("使用感受", _Topic())
    quality = topics.get("质量与耐用", _Topic())
    size = topics.get("尺码与适配", _Topic())
    grip = topics.get("防滑与抓地", _Topic())
    left, right, overlap = (
        size.opposed_pairs[key] for key in ("left", "right", "overlap")
    )
    union = left + right - overlap
    all_feedback = "纳入反馈"
    early = quality.text_signals[EARLY_FAILURE]
    timeline = _timeline(quality, stats)
    location_rows = _quality_location(quality, stats)
    coverage = _coverage(evidence, stats, total, mapped)
    chapters = [
        _chapter(
            "value",
            "产品价值与使用体验",
            "保留用户认可的舒适与贴合"
            if core.positive
            else "当前未观察到可归纳的产品价值",
            [
                _metric("肯定产品核心价值", core.positive, total, all_feedback),
                _metric("涉及使用感受", experience.count, total, all_feedback),
            ],
            _experience_rows(core, experience, total),
            "同一反馈可能同时肯定核心价值、报告质量问题，也可具有正负使用感受。",
            "分子为命中对应主题、方向或标签的反馈，分母为纳入反馈或表中标明的主题子集；同一标签按反馈去重。",
            "舒适与贴合是改款对照，体验负向反馈用于定位需要保护的使用条件。",
            "对照原款和改款的实际试用体验。",
            examples.get(CORE_VALUE_THEME, []) + examples.get("使用感受", []),
        ),
        _chapter(
            "durability",
            "耐用性与短期失效",
            "优先复现短期耐用性问题"
            if quality.negative
            else "当前未观察到质量负向标签",
            [
                _metric("涉及质量主题", quality.count, total, all_feedback),
                _metric("质量负向", quality.negative, total, all_feedback),
                _metric("短期表达命中", early, quality.negative, "质量负向反馈"),
            ],
            _label_rows(quality, quality.count, "涉及质量主题的反馈"),
            "短期表达属于文本规则命中，无法当作已确认故障或故障率。",
            "仅在质量负向反馈中，匹配首用、小时、天或短周表达，排除异常文本；同一反馈只计一次。历史 67 条的规则未保留。",
            "先用实物复验区分首次使用失效和累积磨损，再定位材料及连接处。",
            "P0 复现短期失效并记录出现条件、时间和位置。",
            examples.get(EARLY_FAILURE, []),
        ),
        _chapter(
            "fit",
            "尺码双向不稳定",
            "偏小与偏大需要分别排查" if left and right else "当前双向尺码证据有限",
            [
                _metric("尺码双向范围（去重）", union, total, all_feedback),
                _metric("偏小方向", left, union, "命中任一方向"),
                _metric("偏大方向", right, union, "命中任一方向"),
            ],
            [
                _metric(label, count, union, "命中任一方向")
                for label, count in (
                    ("仅偏小", left - overlap),
                    ("双向", overlap),
                    ("仅偏大", right - overlap),
                    ("单一偏小标签", _small_label(size)),
                )
            ],
            "方向可在同一反馈共存，单一偏小标签比偏小方向更窄。",
            "按分类配置归并偏小、偏紧窄、偏短与偏大、偏松宽、偏长；并集等于两方向总数减去重叠。",
            "一刀切放大或缩小尺码可能把一侧问题转移到另一侧。",
            "P1 在同款同码下分方向对照尺码和贴合反馈。",
            [
                record
                for group in ("仅偏小", "双向", "仅偏大")
                for record in examples.get(group, [])[:1]
            ],
        ),
        _chapter(
            "grip",
            "防滑场景差异",
            "按场景验证防滑卖点" if grip.count else "当前没有可归纳的防滑主题",
            [
                _metric("抓地正向", grip.positive, grip.count, "抓地主题反馈"),
                _metric("抓地负向", grip.negative, grip.count, "抓地主题反馈"),
                _metric(
                    "提及湿滑地面",
                    grip.text_signals["湿滑地面场景"],
                    grip.count,
                    "抓地主题反馈",
                ),
            ],
            [_metric("正负共存", grip.mixed, grip.count, "抓地主题反馈")],
            "情感分类与湿滑文本为分别统计的边际数据，无法据此推断湿滑条件下的负向表现。",
            "目标范围为抓地主题反馈。情感方向与场景文本独立命中，分别按反馈去重。",
            "用对应表面和干湿条件的实物对照确定卖点适用范围。",
            "P1 按干燥与湿滑地面对照验证抓地。",
            examples.get("防滑与抓地", []),
        ),
        _chapter(
            "signals",
            "时间与产品排查信号",
            "按阶段复核耐用差异，商品仅作为排查线索"
            if timeline
            else "当前缺少可比的耐用性时间段",
            timeline,
            location_rows,
            "峰值月包含在较长的比较窗口内。商品主题命中涵盖各情感方向，小样本、商品组合和使用场景均会影响占比。",
            "时间分母是同期纳入反馈。商品只用已匹配反馈，展示质量主题命中与同维度基线；组内样本低于 10 条不展示。",
            "时间差异适合用于抽样复验，商品位置用于缩小排查范围。",
            "对照阶段、商品组合和使用条件是否能解释差异。",
            examples.get(EARLY_FAILURE, [])[:1],
        ),
        _chapter(
            "coverage",
            "数据代表性",
            "反馈可用于排序，发生率需要经营数据",
            coverage[:2],
            coverage[2:],
            "样本集中反映当前反馈结构。缺少销量或订单总量，无法估算总体发生率。",
            "范围来自生成时的看板数据版本。来源待复核、商品已匹配与缺映射分别计数。",
            "保留未匹配反馈用于主题判断，商品级排查以已匹配反馈为基础。",
            "按反馈与销量同范围补齐分母，并复核反馈偏差。",
            (examples.get(CORE_VALUE_THEME, []) + examples.get(EARLY_FAILURE, []))[:1],
        ),
    ]
    evidence["blueprint"]["verifiable"] = {
        "report_type": "verifiable_insight",
        "title": "保留舒适与贴合，先验证耐用性，再解尺码分化"
        if core.positive and quality.negative and left and right
        else "从当前反馈确定产品验证顺序",
        "chapters": chapters,
        "actions": [
            {
                "chapter_id": key,
                "priority": priority,
                "output": output,
                "decision": decision,
            }
            for key, priority, output, decision, active in (
                (
                    "durability",
                    "P0",
                    "复现实验和受损位置",
                    "确定优先更改的材料或连接处",
                    quality.negative,
                ),
                (
                    "fit",
                    "P1",
                    "同款同码、按方向对照的试穿记录",
                    "确定尺码说明或版型调整",
                    union,
                ),
                (
                    "grip",
                    "P1",
                    "干燥与湿滑表面的对照结果",
                    "确定可承诺的防滑条件",
                    grip.count,
                ),
                (
                    "value",
                    "P1",
                    "原款与改款的体验对照结果",
                    "决定需保留的体验特征",
                    core.positive,
                ),
            )
            if active
        ],
        "summary": [
            {"label": "保留", "text": "以已获认可的体验作为改款对照。"},
            {
                "label": "优先验证",
                "text": "P0 先复现短期失效，随后按尺码方向与使用场景验证。"
                if quality.negative
                else "从当前有证据的主题入手验证。",
            },
            {"label": "判断范围", "text": "结论限于当前反馈样本，缺少销量与订单分母。"},
        ],
        "boundaries": evidence["blueprint"]["boundaries"],
    }
    return evidence
