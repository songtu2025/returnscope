from __future__ import annotations

import pandas as pd

from return_semantics.data import ReturnDataset
from return_semantics.exporter import _build_statistics
from return_semantics.schemas import ProcessingStatus, ValidatedClassification
from web_backend.agent_runner_parent_result import ParentResultMixin
from web_backend.review_service import ReviewService


def _classification(
    key: str,
    problem_codes: list[str],
    positive_codes: list[str],
    primary_codes: list[str],
    taxonomy_version: str,
) -> ValidatedClassification:
    return ValidatedClassification(
        classification_key=key,
        semantic_units=[],
        unknown_semantics=[],
        problem_label_codes=problem_codes,
        positive_label_codes=positive_codes,
        primary_label_codes=primary_codes,
        status=ProcessingStatus.AUTO_APPROVED,
        review_reasons=[],
        model_name="test-model",
        prompt_version="test",
        taxonomy_version=taxonomy_version,
    )


def test_problem_label_metrics_match_task_review_and_export(taxonomy) -> None:
    records = pd.DataFrame(
        [
            {"classification_key": "repeat", "has_text_evidence": True},
            {"classification_key": "repeat", "has_text_evidence": True},
            {"classification_key": "single", "has_text_evidence": True},
            {"classification_key": "no-text", "has_text_evidence": False},
        ]
    )
    dataset = ReturnDataset(records, pd.DataFrame(), frozenset())
    results = {
        "repeat": _classification(
            "repeat",
            ["FIT_TOO_SMALL", "FIT_TOO_LARGE"],
            ["EXPERIENCE_COMFORT"],
            ["FIT_TOO_SMALL"],
            taxonomy.version,
        ),
        "single": _classification(
            "single", ["FIT_TOO_LARGE"], [], ["FIT_TOO_LARGE"], taxonomy.version
        ),
    }

    expected = [
        {
            "code": "FIT_TOO_LARGE",
            "name": "偏大",
            "group": "尺码与合脚",
            "count": 3,
            "share": 100.0,
        },
        {
            "code": "FIT_TOO_SMALL",
            "name": "偏小",
            "group": "尺码与合脚",
            "count": 2,
            "share": 66.67,
        },
    ]
    assert ParentResultMixin._top_problem_labels(dataset, results, taxonomy) == expected
    assert ReviewService._top_problem_labels(dataset, results, taxonomy) == expected

    rows = _build_statistics(dataset, results, taxonomy)
    assert [(row["统计类型"], row["标签编码"], row["退货记录数"]) for row in rows] == [
        ("问题标签", "FIT_TOO_LARGE", 3),
        ("问题标签", "FIT_TOO_SMALL", 2),
        ("正面标签", "EXPERIENCE_COMFORT", 2),
        ("主因标签", "FIT_TOO_SMALL", 2),
        ("主因标签", "FIT_TOO_LARGE", 1),
    ]
