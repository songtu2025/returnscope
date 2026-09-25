from __future__ import annotations

from pathlib import Path
from typing import cast

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from return_semantics.data import ReturnDataset
from return_semantics.label_statistics import weighted_label_counts
from return_semantics.schemas import (
    ProcessingStatus,
    TaxonomyConfig,
    ValidatedClassification,
)
from return_semantics.semantic_review import (
    build_semantic_review_view,
)
from return_semantics.taxonomy_hierarchy import label_path, label_path_codes

REVIEW_STATUSES = {
    ProcessingStatus.SECONDARY_REVIEW.value,
    ProcessingStatus.MANUAL_REVIEW.value,
    ProcessingStatus.UNKNOWN_SEMANTIC.value,
    ProcessingStatus.MODEL_ERROR.value,
}


def _format_labels(codes: list[str], label_names: dict[str, str]) -> str:
    return " | ".join(f"{code}:{label_names.get(code, '')}" for code in codes)


def _path_columns(taxonomy: TaxonomyConfig, code: str) -> dict[str, str]:
    path = label_path(taxonomy, code)
    return {
        "完整路径": " → ".join(path),
        "标签编码路径": " → ".join(label_path_codes(taxonomy, code)),
        **{f"第{index}级标签": name for index, name in enumerate(path, 1)},
    }


def _display_key(classification_key: str) -> str:
    return "".join(
        character if ord(character) >= 32 else " " for character in classification_key
    )


def _format_relations(result: ValidatedClassification) -> str:
    return " | ".join(
        f"{relation.relation_type.value}:"
        f"{','.join(relation.fact_ids)}:{relation.reason}"
        for relation in result.semantic_relations
    )


def _build_detail_rows(
    dataset: ReturnDataset,
    results: dict[str, ValidatedClassification],
    taxonomy: TaxonomyConfig,
) -> list[dict[str, object]]:
    label_names = {label.code: label.name for label in taxonomy.labels}
    rows = []
    for record in dataset.records.to_dict(orient="records"):
        if not record.get("category_a") or not record.get("category_b"):
            result = None
            status = "EXCLUDED_MISSING_CATEGORY"
        elif not record["has_text_evidence"]:
            result = None
            status = ProcessingStatus.NO_TEXT_EVIDENCE.value
        else:
            result = results.get(record["classification_key"])
            status = result.status.value if result is not None else "PENDING"

        units = result.semantic_units if result is not None else []
        rows.append(
            {
                "源数据行号": record["source_row"],
                "分类键": _display_key(record["classification_key"]),
                "return-date": record["return-date"],
                "order-id": record["order-id"],
                "sku": record.get("source_sku", record.get("sku_raw", "")),
                "source_sku": record.get("source_sku", record.get("sku_raw", "")),
                "matched_msku": record.get("matched_msku", ""),
                "product_sku": record.get("product_sku", ""),
                "asin": record["asin"],
                "店铺/站点": record.get("store", ""),
                "Listing": record.get("listing", ""),
                "产品名称": record.get("product_name", ""),
                "商品匹配状态": record.get("product_match_status", "unmatched"),
                "品类A": record.get("category_a", ""),
                "品类B": record.get("category_b", ""),
                "Amazon原因": record["reason"],
                "评论原文": record["comment_raw"],
                "标准化评论": record["comment_normalized"],
                "问题标签": _format_labels(
                    result.problem_label_codes if result else [],
                    label_names,
                ),
                "正面标签": _format_labels(
                    result.positive_label_codes if result else [],
                    label_names,
                ),
                "主因标签": _format_labels(
                    result.primary_label_codes if result else [],
                    label_names,
                ),
                "完整标签路径": " | ".join(
                    " → ".join(label_path(taxonomy, unit.label_code)) for unit in units
                ),
                "事实编号": " | ".join(
                    ",".join(unit.fact_ids or ([unit.fact_id] if unit.fact_id else []))
                    for unit in units
                ),
                "使用者引用": " | ".join(unit.actor_ref for unit in units),
                "观点来源引用": " | ".join(unit.source_ref for unit in units),
                "实际体验者引用": " | ".join(unit.experiencer_ref for unit in units),
                "商品引用": " | ".join(unit.product_ref for unit in units),
                "规格引用": " | ".join(unit.variant_ref for unit in units),
                "事件引用": " | ".join(unit.event_ref for unit in units),
                "比较基准": " | ".join(unit.reference_basis.value for unit in units),
                "陈述类型": " | ".join(unit.statement_type for unit in units),
                "事实角色": " | ".join(unit.fact_role.value for unit in units),
                "操作": " | ".join(unit.operation for unit in units),
                "条件": " | ".join(unit.condition for unit in units),
                "部位": " | ".join(unit.part for unit in units),
                "因果归属": " | ".join(unit.causal_attribution.value for unit in units),
                "因果说明": " | ".join(
                    unit.causal_attribution_reason for unit in units
                ),
                "判定理由": " | ".join(unit.decision_reason for unit in units),
                "证据原文": " | ".join(unit.evidence for unit in units),
                "证据来源": " | ".join(unit.evidence_source.value for unit in units),
                "未映射处置": " | ".join(
                    item.disposition.value
                    for item in (result.unknown_semantics if result else [])
                ),
                "评论摘要状态": (result.comment_summary.status.value if result else ""),
                "语义关系": _format_relations(result) if result else "",
                "Listing承诺关系": " | ".join(
                    unit.claim_relation.value for unit in units
                ),
                "Listing承诺编号": " | ".join(unit.claim_id or "" for unit in units),
                "处理状态": status,
                "复核原因": " | ".join(result.review_reasons if result else []),
                "模型": result.model_name if result else "",
                "提示版本": result.prompt_version if result else "",
                "分类体系版本": result.taxonomy_version if result else "",
            }
        )
    return rows


def _build_semantic_rows(
    dataset: ReturnDataset,
    results: dict[str, ValidatedClassification],
    taxonomy: TaxonomyConfig,
) -> list[dict[str, object]]:
    labels = {label.code: label for label in taxonomy.labels}
    unique_map = dataset.unique_comments.set_index("classification_key")
    rows = []
    for classification_key, result in results.items():
        source = unique_map.loc[classification_key]
        for index, unit in enumerate(result.semantic_units, start=1):
            label = labels[unit.label_code]
            rows.append(
                {
                    "分类键": _display_key(classification_key),
                    "语义序号": index,
                    "重复记录数": source["record_count"],
                    "Amazon原因": source["reason"],
                    "标准化评论": source["comment_normalized"],
                    "标签编码": unit.label_code,
                    "标签名称": label.name,
                    "一级分类": label.group,
                    **_path_columns(taxonomy, label.code),
                    "对象": unit.subject.value,
                    "事实编号": ",".join(
                        unit.fact_ids or ([unit.fact_id] if unit.fact_id else [])
                    ),
                    "使用者引用": unit.actor_ref,
                    "观点来源引用": unit.source_ref,
                    "实际体验者引用": unit.experiencer_ref,
                    "商品引用": unit.product_ref,
                    "规格引用": unit.variant_ref,
                    "事件引用": unit.event_ref,
                    "比较基准": unit.reference_basis.value,
                    "陈述类型": unit.statement_type,
                    "事实角色": unit.fact_role.value,
                    "操作": unit.operation,
                    "观点": unit.opinion,
                    "中文事实": unit.opinion,
                    "正负面": unit.sentiment.value,
                    "断言状态": unit.assertion.value,
                    "部位": unit.part,
                    "条件": unit.condition,
                    "因果归属": unit.causal_attribution.value,
                    "因果说明": unit.causal_attribution_reason,
                    "判定理由": unit.decision_reason,
                    "上下文事实编号": ",".join(unit.context_fact_ids),
                    "证据原文": unit.evidence,
                    "证据来源": unit.evidence_source.value,
                    "是否隐含": unit.implicit,
                    "Listing承诺关系": unit.claim_relation.value,
                    "Listing承诺编号": unit.claim_id or "",
                    "处理状态": result.status.value,
                    "评论摘要状态": result.comment_summary.status.value,
                }
            )
    return rows


def _build_unknown_rows(
    dataset: ReturnDataset,
    results: dict[str, ValidatedClassification],
) -> list[dict[str, object]]:
    unique_map = dataset.unique_comments.set_index("classification_key")
    rows = []
    for classification_key, result in results.items():
        source = unique_map.loc[classification_key]
        for unknown in result.unknown_semantics:
            rows.append(
                {
                    "分类键": _display_key(classification_key),
                    "重复记录数": source["record_count"],
                    "Amazon原因": source["reason"],
                    "标准化评论": source["comment_normalized"],
                    "标准化观点": unknown.opinion,
                    "事实编号": unknown.fact_id or "",
                    "使用者引用": unknown.actor_ref,
                    "观点来源引用": unknown.source_ref,
                    "实际体验者引用": unknown.experiencer_ref,
                    "商品引用": unknown.product_ref,
                    "规格引用": unknown.variant_ref,
                    "事件引用": unknown.event_ref,
                    "比较基准": unknown.reference_basis.value,
                    "陈述类型": unknown.statement_type,
                    "事实角色": unknown.fact_role.value,
                    "操作": unknown.operation,
                    "条件": unknown.condition,
                    "因果归属": unknown.causal_attribution.value,
                    "因果说明": unknown.causal_attribution_reason,
                    "证据原文": unknown.evidence,
                    "证据来源": unknown.evidence_source.value,
                    "处置类型": unknown.disposition.value,
                    "未映射原因": unknown.reason,
                }
            )
    return rows


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


def _build_dimension_decision_rows(
    results: dict[str, ValidatedClassification],
) -> list[dict[str, object]]:
    rows = []
    for classification_key, result in results.items():
        for index, decision in enumerate(result.dimension_decisions, start=1):
            rows.append(
                {
                    "分类键": _display_key(classification_key),
                    "裁决序号": index,
                    "父维度编码": decision.parent_code,
                    "结论标签编码": decision.verdict_label_code,
                    "支持事实编号": ",".join(decision.supporting_fact_ids),
                    "上下文事实编号": ",".join(decision.context_fact_ids),
                    "观点来源引用": decision.scope.source_ref,
                    "实际体验者引用": decision.scope.experiencer_ref,
                    "商品引用": decision.scope.product_ref,
                    "规格引用": decision.scope.variant_ref,
                    "事件引用": decision.scope.event_ref,
                    "比较基准": decision.scope.reference_basis.value,
                    "部位": decision.scope.part,
                    "操作": decision.scope.operation,
                    "条件": decision.scope.condition,
                    "裁决理由": decision.reason,
                }
            )
    return rows


def _build_statistics(
    dataset: ReturnDataset,
    results: dict[str, ValidatedClassification],
    taxonomy: TaxonomyConfig,
) -> list[dict[str, object]]:
    labels = {label.code: label for label in taxonomy.labels}
    problem_counts, positive_counts, primary_counts = weighted_label_counts(
        dataset, results
    )

    rows = []
    for metric, counts in (
        ("问题标签", problem_counts),
        ("正面标签", positive_counts),
        ("主因标签", primary_counts),
    ):
        for code, count in counts.most_common():
            label = labels[code]
            rows.append(
                {
                    "统计类型": metric,
                    "标签编码": code,
                    "标签名称": label.name,
                    "一级分类": label.group,
                    **_path_columns(taxonomy, label.code),
                    "退货记录数": count,
                }
            )
    return rows


def _style_workbook(writer: pd.ExcelWriter) -> None:
    header_fill = PatternFill("solid", fgColor="D9EAF7")
    for sheet in writer.book.worksheets:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for column_index, column_cells in enumerate(sheet.columns, 1):
            values = [str(cell.value or "") for cell in column_cells[:200]]
            width = min(max(max(map(len, values), default=10) + 2, 12), 50)
            sheet.column_dimensions[get_column_letter(column_index)].width = width


def export_results(
    output_path: Path,
    dataset: ReturnDataset,
    results: dict[str, ValidatedClassification],
    taxonomy: TaxonomyConfig,
) -> None:
    detail = pd.DataFrame(_build_detail_rows(dataset, results, taxonomy))
    semantics = pd.DataFrame(_build_semantic_rows(dataset, results, taxonomy))
    unknown = pd.DataFrame(_build_unknown_rows(dataset, results))
    semantic_review = pd.DataFrame(
        _build_semantic_review_rows(dataset, results, taxonomy)
    )
    if semantic_review.empty:
        business_review = semantic_review.copy()
        system_rerun = semantic_review.copy()
    else:
        system_rerun = semantic_review.loc[
            semantic_review["处置状态"].isin(["ANALYSIS_FAILURE", "MODEL_ERROR"])
            & semantic_review["是否需要业务判断"].eq("否")
        ].copy()
        system_rerun_keys = set(system_rerun["分类键"])
        business_review = semantic_review.loc[
            semantic_review["是否需要业务判断"].eq("是")
            & ~semantic_review["分类键"].isin(system_rerun_keys)
        ].copy()
    decisions = pd.DataFrame(_build_dimension_decision_rows(results))
    statistics = pd.DataFrame(_build_statistics(dataset, results, taxonomy))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        detail.to_excel(writer, sheet_name="分类明细", index=False)
        semantics.to_excel(writer, sheet_name="语义单元", index=False)
        business_review.to_excel(writer, sheet_name="人工复核", index=False)
        system_rerun.to_excel(writer, sheet_name="系统待重跑", index=False)
        unknown.to_excel(writer, sheet_name="未知语义", index=False)
        semantic_review.to_excel(writer, sheet_name="语义核验", index=False)
        decisions.to_excel(writer, sheet_name="维度裁决", index=False)
        statistics.to_excel(writer, sheet_name="标签统计", index=False)
        _style_workbook(writer)
