from __future__ import annotations

from typing import cast

from return_semantics.data import ReturnDataset
from return_semantics.export_formatting import _display_key
from return_semantics.schemas import TaxonomyConfig, ValidatedClassification
from return_semantics.semantic_review import build_semantic_review_view


def _build_semantic_review_rows(
    dataset: ReturnDataset,
    results: dict[str, ValidatedClassification],
    taxonomy: TaxonomyConfig,
) -> list[dict[str, object]]:
    unique_map = dataset.unique_comments.set_index("classification_key")
    rows = []
    for classification_key, result in results.items():
        source = unique_map.loc[classification_key]
        source_text = str(source["comment_normalized"] or "")
        view = build_semantic_review_view(result, source_text, taxonomy)
        summary = cast(dict[str, object], view["coverage_summary"])
        unexplained_fragments = cast(list[str], view["unexplained_fragments"])
        unexplained = " | ".join(unexplained_fragments)
        items = cast(list[dict[str, object]], view["semantic_items"]) or [
            {
                "item_id": "",
                "fact_id": "",
                "evidence_text": "",
                "evidence_source": "",
                "opinion": "",
                "label_code": "",
                "label_path": [],
                "disposition": "",
                "reason": "",
                "diagnostic_domain": "",
                "diagnostic_code": "",
                "diagnostic_title": "",
                "detail_status": "",
                "primary_result": "",
                "secondary_result": "",
                "detail": "",
                "action": "",
                "business_review_required": "",
            }
        ]
        for index, item in enumerate(items, start=1):
            rows.append(
                {
                    "分类键": _display_key(classification_key),
                    "语义序号": index,
                    "核验项编号": item["item_id"],
                    "事实编号": item["fact_id"],
                    "重复记录数": source["record_count"],
                    "Amazon原因": source["reason"],
                    "标准化评论": source_text,
                    "证据原文": item["evidence_text"],
                    "证据来源": item["evidence_source"],
                    "提取观点": item["opinion"],
                    "标签编码": item["label_code"],
                    "标签路径": " → ".join(cast(list[str], item["label_path"])),
                    "处置状态": item["disposition"],
                    "处置说明": item["reason"],
                    "异常归属": {
                        "TECHNICAL_RUNTIME": "技术运行失败",
                        "TECHNICAL_CONFIGURATION": "系统配置异常",
                        "SEMANTIC_ANALYSIS_QUALITY": "语义分析质量异常",
                    }.get(str(item.get("diagnostic_domain", "")), ""),
                    "诊断编码": item.get("diagnostic_code", ""),
                    "异常类型": item.get("diagnostic_title", ""),
                    "差异明细状态": {
                        "AVAILABLE": "已保留",
                        "NOT_RETAINED": "未保留",
                        "NOT_APPLICABLE": "不适用",
                    }.get(str(item.get("detail_status", "")), ""),
                    "是否需要业务判断": (
                        "是"
                        if item.get("business_review_required") is True
                        else "否"
                        if item.get("business_review_required") is False
                        else ""
                    ),
                    "首次分析结果": item.get("primary_result", ""),
                    "复核分析结果": item.get("secondary_result", ""),
                    "差异明细": item.get("detail", ""),
                    "处理建议": item.get("action", ""),
                    "未解释原文片段": unexplained,
                    "覆盖是否完整": "是" if summary["complete"] else "否",
                    "已归类数": summary["mapped"],
                    "无需标签数": summary["no_tag_needed"],
                    "标签体系缺口数": summary["taxonomy_gap"],
                    "真实歧义数": summary["true_ambiguity"],
                    "分析失败数": summary["analysis_failure"],
                    "人工判断": "",
                    "人工修改标签": "",
                    "人工备注": "",
                }
            )
    return rows
