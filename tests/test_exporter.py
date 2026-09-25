from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from return_semantics.data import ReturnDataset
from return_semantics.exporter import export_results
from return_semantics.schemas import ValidatedClassification


def test_exporter_creates_expected_sheets(tmp_path: Path, taxonomy) -> None:
    classification_key = "APPAREL_TOO_SMALL\x1ftoo small"
    business_classification_key = "APPAREL_TOO_SMALL\x1ftoo narrow"
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
            },
            {
                "source_row": 3,
                "return-date": "2026-01-02",
                "order-id": "ORDER-2",
                "sku": "SKU-1",
                "asin": "ASIN-1",
                "reason": "APPAREL_TOO_SMALL",
                "comment_raw": "Too narrow",
                "comment_normalized": "Too narrow",
                "has_text_evidence": True,
                "classification_key": business_classification_key,
                "category_a": "水鞋",
                "category_b": "薄底水鞋",
            },
        ]
    )
    unique_comments = pd.DataFrame(
        [
            {
                "classification_key": classification_key,
                "reason": "APPAREL_TOO_SMALL",
                "comment_normalized": "Too small",
                "record_count": 1,
            },
            {
                "classification_key": business_classification_key,
                "reason": "APPAREL_TOO_SMALL",
                "comment_normalized": "Too narrow",
                "record_count": 1,
            },
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
            "status": "AUTO_APPROVED",
            "review_reasons": [],
            "review_diagnostics": [
                {
                    "code": "MODEL_RESULT_MISMATCH",
                    "evidence_text": "Too small",
                    "primary_result": "尺码偏小",
                    "secondary_result": "尺码正常",
                    "detail": "两次模型对尺码结论不同",
                    "action": "请业务员核对尺码标签。",
                },
                {
                    "code": "SECONDARY_MODEL_TIMEOUT",
                    "evidence_text": "Too small",
                    "primary_result": "尺码偏小",
                    "secondary_result": "",
                    "detail": "风险复核超时",
                    "action": "SYSTEM_RERUN",
                },
            ],
            "model_name": "test-model",
            "prompt_version": "test-prompt",
            "taxonomy_version": taxonomy.version,
        }
    )
    business_result_payload = result.model_dump()
    business_result_payload.update(
        {
            "classification_key": business_classification_key,
            "review_diagnostics": [
                {
                    "code": "MODEL_RESULT_MISMATCH",
                    "evidence_text": "Too narrow",
                    "primary_result": "鞋楦偏窄",
                    "secondary_result": "尺码正常",
                    "detail": "两次模型对宽度结论不同",
                    "action": "请业务员核对宽度标签。",
                }
            ],
        }
    )
    business_result = ValidatedClassification.model_validate(business_result_payload)
    output_path = tmp_path / "result.xlsx"

    export_results(
        output_path,
        dataset,
        {
            classification_key: result,
            business_classification_key: business_result,
        },
        taxonomy,
    )

    workbook = load_workbook(output_path, read_only=True)
    assert workbook.sheetnames == [
        "分类明细",
        "语义单元",
        "人工复核",
        "系统待重跑",
        "未知语义",
        "语义核验",
        "维度裁决",
        "标签统计",
    ]
    assert workbook["分类明细"].max_row == 3
    assert workbook["维度裁决"].max_row == 3

    business_review = pd.read_excel(output_path, sheet_name="人工复核", dtype=str)
    system_rerun = pd.read_excel(output_path, sheet_name="系统待重跑", dtype=str)
    semantic_review = pd.read_excel(output_path, sheet_name="语义核验", dtype=str)
    statistics = pd.read_excel(output_path, sheet_name="标签统计")

    assert business_review["诊断编码"].tolist() == ["MODEL_RESULT_MISMATCH"]
    assert statistics.loc[
        statistics["统计类型"] == "问题标签", ["标签编码", "退货记录数"]
    ].to_dict("records") == [{"标签编码": "FIT_TOO_SMALL", "退货记录数": 2}]
    assert business_review["是否需要业务判断"].tolist() == ["是"]
    assert business_review["分类键"].tolist() == ["APPAREL_TOO_SMALL too narrow"]
    assert system_rerun["诊断编码"].tolist() == ["SECONDARY_MODEL_TIMEOUT"]
    assert system_rerun["是否需要业务判断"].tolist() == ["否"]
    assert system_rerun["分类键"].tolist() == ["APPAREL_TOO_SMALL too small"]
    assert {
        "MODEL_RESULT_MISMATCH",
        "SECONDARY_MODEL_TIMEOUT",
    }.issubset(set(semantic_review["诊断编码"].dropna()))


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
