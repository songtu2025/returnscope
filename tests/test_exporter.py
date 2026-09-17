from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from return_semantics.data import ReturnDataset
from return_semantics.exporter import export_results
from return_semantics.schemas import ValidatedClassification


def test_exporter_creates_expected_sheets(tmp_path: Path, taxonomy) -> None:
    classification_key = "APPAREL_TOO_SMALL\x1ftoo small"
    records = pd.DataFrame(
        [
            {
                "source_row": 2,
                "return-date": "2026-01-01",
                "order-id": "ORDER-1",
                "sku": "SKU-1",
                "asin": "ASIN-1",
                "reason": "APPAREL_TOO_SMALL",
                "comment_raw": "Too small",
                "comment_normalized": "Too small",
                "has_text_evidence": True,
                "classification_key": classification_key,
                "category_a": "水鞋",
                "category_b": "薄底水鞋",
            }
        ]
    )
    unique_comments = pd.DataFrame(
        [
            {
                "classification_key": classification_key,
                "reason": "APPAREL_TOO_SMALL",
                "comment_normalized": "Too small",
                "record_count": 1,
            }
        ]
    )
    dataset = ReturnDataset(
        records=records,
        unique_comments=unique_comments,
        mskus=frozenset({"SKU-1"}),
    )
    result = ValidatedClassification.model_validate(
        {
            "classification_key": classification_key,
            "semantic_units": [
                {
                    "subject": "PRODUCT",
                    "label_code": "FIT_TOO_SMALL",
                    "opinion": "尺码偏小",
                    "sentiment": "NEGATIVE",
                    "assertion": "AFFIRMED",
                    "part": "WHOLE_SHOE",
                    "evidence": "Too small",
                    "implicit": False,
                    "claim_relation": "NONE",
                    "claim_id": None,
                }
            ],
            "unknown_semantics": [],
            "dimension_decisions": [
                {
                    "parent_code": "FIT",
                    "scope": {
                        "product_ref": "CURRENT",
                        "variant_ref": "M",
                    },
                    "verdict_label_code": "FIT_TOO_SMALL",
                    "supporting_fact_ids": ["F1"],
                    "context_fact_ids": ["F2"],
                    "reason": "完整评价表明尺码偏小",
                }
            ],
            "problem_label_codes": ["FIT_TOO_SMALL"],
            "positive_label_codes": [],
            "primary_label_codes": ["FIT_TOO_SMALL"],
            "status": "MANUAL_REVIEW",
            "review_reasons": ["二次模型调用失败: 请求超时"],
            "review_diagnostics": [
                {
                    "code": "SECONDARY_MODEL_TIMEOUT",
                    "detail": "请求超时",
                    "action": "SYSTEM_RERUN",
                }
            ],
            "model_name": "test-model",
            "prompt_version": "test-prompt",
            "taxonomy_version": taxonomy.version,
        }
    )
    output_path = tmp_path / "result.xlsx"

    export_results(
        output_path,
        dataset,
        {classification_key: result},
        taxonomy,
    )

    workbook = load_workbook(output_path, read_only=True)
    assert workbook.sheetnames == [
        "分类明细",
        "语义单元",
        "人工复核",
        "未知语义",
        "语义核验",
        "维度裁决",
        "标签统计",
    ]
    assert workbook["分类明细"].max_row == 2
    assert workbook["人工复核"].max_row == 1
    assert workbook["维度裁决"].max_row == 2
    review_sheet = workbook["语义核验"]
    headers = [cell.value for cell in next(review_sheet.iter_rows())]
    first_row = {
        header: cell.value
        for header, cell in zip(
            headers,
            next(review_sheet.iter_rows(min_row=2)),
            strict=True,
        )
    }
    assert first_row["证据原文"] == "Too small"
    assert first_row["提取观点"] == "尺码偏小"
    assert first_row["标签编码"] == "FIT_TOO_SMALL"
    assert first_row["处置状态"] == "MAPPED"
    assert first_row["异常归属"] is None
    assert first_row["处理建议"] is None
    assert first_row["人工判断"] is None
    failure_row = {
        header: cell.value
        for header, cell in zip(
            headers,
            next(review_sheet.iter_rows(min_row=3)),
            strict=True,
        )
    }
    assert failure_row["处置状态"] == "ANALYSIS_FAILURE"
    assert failure_row["异常归属"] == "技术运行失败"
    assert failure_row["诊断编码"] == "SECONDARY_MODEL_TIMEOUT"
    assert failure_row["异常类型"] == "风险复核调用超时"
    assert failure_row["差异明细状态"] == "不适用"
    assert failure_row["是否需要业务判断"] == "否"
    assert failure_row["处理建议"] == "无需业务员核验；请系统重试风险复核。"


def test_exporter_marks_missing_category_as_excluded(tmp_path: Path, taxonomy) -> None:
    classification_key = "SKU=SKU-2\x1fUNKNOWN\x1fnot configured"
    records = pd.DataFrame(
        [
            {
                "source_row": 2,
                "return-date": "2026-01-01",
                "order-id": "ORDER-2",
                "sku": "SKU-2",
                "asin": "ASIN-2",
                "reason": "UNKNOWN",
                "comment_raw": "Not configured",
                "comment_normalized": "Not configured",
                "has_text_evidence": True,
                "classification_key": classification_key,
                "category_a": "",
                "category_b": "",
            }
        ]
    )
    unique_comments = pd.DataFrame(
        [
            {
                "classification_key": classification_key,
                "reason": "UNKNOWN",
                "comment_normalized": "Not configured",
                "record_count": 1,
            }
        ]
    )
    dataset = ReturnDataset(
        records=records,
        unique_comments=unique_comments,
        mskus=frozenset({"SKU-2"}),
    )
    output_path = tmp_path / "excluded.xlsx"

    export_results(output_path, dataset, {}, taxonomy)

    detail = pd.read_excel(output_path, sheet_name="分类明细", dtype=str)
    assert detail.loc[0, "处理状态"] == "EXCLUDED_MISSING_CATEGORY"
