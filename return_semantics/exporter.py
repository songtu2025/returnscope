from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill

from return_semantics.data import ReturnDataset
from return_semantics.schemas import (
    ProcessingStatus,
    TaxonomyConfig,
    ValidatedClassification,
)

REVIEW_STATUSES = {
    ProcessingStatus.SECONDARY_REVIEW.value,
    ProcessingStatus.MANUAL_REVIEW.value,
    ProcessingStatus.UNKNOWN_SEMANTIC.value,
    ProcessingStatus.MODEL_ERROR.value,
}


def _format_labels(codes: list[str], label_names: dict[str, str]) -> str:
    return " | ".join(f"{code}:{label_names.get(code, '')}" for code in codes)


def _display_key(classification_key: str) -> str:
    return "".join(
        character if ord(character) >= 32 else " " for character in classification_key
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
                "部位": " | ".join(unit.part.value for unit in units),
                "证据原文": " | ".join(unit.evidence for unit in units),
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
                    "对象": unit.subject.value,
                    "观点": unit.opinion,
                    "正负面": unit.sentiment.value,
                    "断言状态": unit.assertion.value,
                    "部位": unit.part.value,
                    "证据原文": unit.evidence,
                    "是否隐含": unit.implicit,
                    "Listing承诺关系": unit.claim_relation.value,
                    "Listing承诺编号": unit.claim_id or "",
                    "处理状态": result.status.value,
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
                    "证据原文": unknown.evidence,
                    "未映射原因": unknown.reason,
                }
            )
    return rows


def _build_statistics(
    dataset: ReturnDataset,
    results: dict[str, ValidatedClassification],
    taxonomy: TaxonomyConfig,
) -> list[dict[str, object]]:
    labels = {label.code: label for label in taxonomy.labels}
    problem_counts: Counter[str] = Counter()
    positive_counts: Counter[str] = Counter()
    primary_counts: Counter[str] = Counter()

    record_counts = dataset.records["classification_key"].value_counts()
    for classification_key, result in results.items():
        weight = int(record_counts.get(classification_key, 0))
        problem_counts.update({code: weight for code in result.problem_label_codes})
        positive_counts.update({code: weight for code in result.positive_label_codes})
        primary_counts.update({code: weight for code in result.primary_label_codes})

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

        for column_cells in sheet.columns:
            values = [str(cell.value or "") for cell in column_cells[:200]]
            width = min(max(max(map(len, values), default=10) + 2, 12), 50)
            sheet.column_dimensions[column_cells[0].column_letter].width = width


def export_results(
    output_path: Path,
    dataset: ReturnDataset,
    results: dict[str, ValidatedClassification],
    taxonomy: TaxonomyConfig,
) -> None:
    detail = pd.DataFrame(_build_detail_rows(dataset, results, taxonomy))
    semantics = pd.DataFrame(_build_semantic_rows(dataset, results, taxonomy))
    review_counts = detail["分类键"].value_counts()
    review = (
        detail.loc[detail["处理状态"].isin(REVIEW_STATUSES)]
        .drop_duplicates(subset=["分类键"])
        .copy()
    )
    review.insert(2, "重复记录数", review["分类键"].map(review_counts))
    unknown = pd.DataFrame(_build_unknown_rows(dataset, results))
    statistics = pd.DataFrame(_build_statistics(dataset, results, taxonomy))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        detail.to_excel(writer, sheet_name="分类明细", index=False)
        semantics.to_excel(writer, sheet_name="语义单元", index=False)
        review.to_excel(writer, sheet_name="人工复核", index=False)
        unknown.to_excel(writer, sheet_name="未知语义", index=False)
        statistics.to_excel(writer, sheet_name="标签统计", index=False)
        _style_workbook(writer)
