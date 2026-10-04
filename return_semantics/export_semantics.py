from __future__ import annotations

from return_semantics.data import ReturnDataset
from return_semantics.export_formatting import _display_key, _path_columns
from return_semantics.label_statistics import weighted_label_counts
from return_semantics.schemas import TaxonomyConfig, ValidatedClassification


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
