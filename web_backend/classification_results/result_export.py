"""将详情页已有反馈分组和证据清单投影为中文复核表。"""

from __future__ import annotations

from typing import Any

QUALITY_LABELS = {
    "ready": "可用",
    "review_required": "需复核",
    "unusable": "不可用",
    "excluded": "已忽略",
}
SEMANTIC_LABELS = {
    "POSITIVE": "仅正向",
    "NEGATIVE": "仅负向",
    "MIXED": "混合表现",
    "CONFLICT": "疑似冲突",
    "NO_CONFIRMED": "无确定评价",
}
DISPOSITION_LABELS = {
    "MAPPED": "已归类",
    "NO_TAG_NEEDED": "无需归类",
    "TAXONOMY_GAP": "标签体系缺口",
    "TRUE_AMBIGUITY": "原文含义不明确",
    "ANALYSIS_FAILURE": "系统处理失败",
    "UNEXPLAINED": "未解释原文片段",
}

SUMMARY_COLUMNS = [
    "反馈编号",
    "订单号",
    "产品名称",
    "反馈正文",
    "中文语义",
    "分类路径",
    "结果状态",
    "语义状态",
    "是否需重跑",
    "人工修正情况",
    "修正人",
    "修正时间",
    "源明细数",
    "店铺/站点",
    "Listing",
    "来源SKU（MSKU）",
    "产品SKU",
    "反馈日期",
    "反馈标题 / 原因",
]
SEMANTIC_COLUMNS = [
    "反馈编号",
    "语义序号",
    "中文语义",
    "分类路径",
    "原文证据",
    "处置状态",
    "判断说明",
    "标签代码",
]
SOURCE_FIELDS = {
    "源记录编号": "source_record_id",
    "源文件行号": "source_row",
    "来源标识": "source_origin_id",
    "结果版本编号": "result_version_id",
    "日期": "return_date",
    "订单号": "order_id",
    "店铺/站点": "store_site",
    "Listing": "listing",
    "产品名称": "product_name",
    "来源SKU（MSKU）": "source_sku",
    "匹配MSKU": "matched_msku",
    "产品SKU": "product_sku",
    "ASIN": "asin",
    "FNSKU": "fnsku",
    "品类A": "category_a",
    "品类B": "category_b",
    "反馈标题 / 原因": "reason",
    "反馈正文": "comment",
}
SOURCE_COLUMNS = ["反馈编号", *SOURCE_FIELDS, "产品匹配"]


def semantic_export_rows(
    item: dict[str, Any], feedback_id: str
) -> list[dict[str, Any]]:
    review = item["classification"].get("semantic_review", {})
    items = [
        *review.get("semantic_items", []),
        *(
            {
                "opinion": "原文片段尚未获得语义处置",
                "evidence_text": fragment,
                "disposition": "UNEXPLAINED",
                "reason": "请判断该片段是否需要归类",
            }
            for fragment in review.get("unexplained_fragments", [])
        ),
    ]
    return [
        {
            "反馈编号": feedback_id,
            "语义序号": index,
            "中文语义": unit.get("opinion") or "未形成中文语义",
            "分类路径": " → ".join(unit.get("label_path") or [])
            or ("分类路径未提供" if unit.get("label_code") else "未归类"),
            "原文证据": unit.get("evidence_text") or "",
            "处置状态": DISPOSITION_LABELS.get(str(unit.get("disposition")), "待判断"),
            "判断说明": unit.get("reason") or "",
            "标签代码": unit.get("label_code") or "",
        }
        for index, unit in enumerate(items, 1)
    ]


def feedback_export_row(
    group: dict[str, Any], feedback_id: str, semantics: list[dict[str, Any]]
) -> dict[str, Any]:
    item = group["record"]
    assessment = item["classification"].get("human_review_assessment") or {}
    return {
        "反馈编号": feedback_id,
        "订单号": item.get("order_id"),
        "产品名称": item.get("product_name"),
        "反馈日期": item.get("return_date"),
        "反馈标题 / 原因": item.get("reason"),
        "反馈正文": item.get("comment"),
        "中文语义": _numbered(semantics, "中文语义") or "未形成语义",
        "分类路径": _numbered(semantics, "分类路径") or "未归类",
        "结果状态": QUALITY_LABELS.get(item.get("quality_status"), "状态未提供"),
        "语义状态": SEMANTIC_LABELS.get(
            item.get("comment_summary_status"), "无确定评价"
        ),
        "是否需重跑": "是" if item["system_rerun_required"] else "否",
        "人工修正情况": "人工已修正" if assessment.get("resolved") else "未人工修正",
        "修正人": assessment.get("assessed_by_name") or "",
        "修正时间": assessment.get("assessed_at") or "",
        "源明细数": group["member_count"],
        "店铺/站点": item.get("store_site"),
        "Listing": item.get("listing"),
        "来源SKU（MSKU）": item.get("source_sku"),
        "产品SKU": item.get("product_sku"),
    }


def _numbered(rows: list[dict[str, Any]], column: str) -> str:
    return "\n".join(f"{row['语义序号']}. {row[column]}" for row in rows)


def source_export_rows(rows: list[Any], feedback_id: str) -> list[dict[str, Any]]:
    records = [dict(row) for row in rows]
    return [
        {
            "反馈编号": feedback_id,
            **{label: record.get(field) for label, field in SOURCE_FIELDS.items()},
            "产品匹配": "已匹配"
            if record.get("product_match_status") == "matched"
            else "未匹配",
        }
        for record in records
    ]
