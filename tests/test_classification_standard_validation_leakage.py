from __future__ import annotations

from typing import Any

import pytest

from web_backend.classification_standard_validation_leakage import (
    find_taxonomy_sample_leaks,
    format_taxonomy_sample_leaks,
)
from web_backend.classification_standard_validation_service import (
    ClassificationStandardValidationService,
)


def _taxonomy(**label_changes: Any) -> dict[str, Any]:
    label = {
        "code": "FIT_COMFORT",
        "name": "佩戴舒适",
        "description": "明确评价商品长时间佩戴时没有压迫或疼痛",
        "exclusions": ["只描述外观时不适用"],
        "examples": [],
    }
    label.update(label_changes)
    return {"labels": [label]}


def _sample(review_id: str, comment: str) -> dict[str, str]:
    return {"review_id": review_id, "comment": comment}


def test_detects_sample_identifier_in_example_explanation() -> None:
    taxonomy = _taxonomy(
        examples=[
            {
                "text": "适合日常使用",
                "explanation": "来自样本 Review-Ab12Cd34 的判断",
            }
        ]
    )

    issues = find_taxonomy_sample_leaks(
        taxonomy,
        [_sample("review-ab12cd34", "The gloves are comfortable for daily use.")],
    )

    assert issues == [
        {
            "label_code": "FIT_COMFORT",
            "label_name": "佩戴舒适",
            "field": "示例 1 说明",
            "review_id": "review-ab12cd34",
            "match_type": "review_id",
        }
    ]


def test_detects_near_duplicate_long_comment_without_identifier() -> None:
    comment = (
        "The gloves fit comfortably and the lining stays soft during long winter "
        "walks, even when the temperature drops below freezing."
    )
    taxonomy = _taxonomy(
        examples=[
            {
                "text": comment.replace("soft", "smooth"),
                "explanation": "完整使用体验",
            }
        ]
    )

    issues = find_taxonomy_sample_leaks(
        taxonomy,
        [_sample("sample-without-public-id", comment)],
    )

    assert len(issues) == 1
    assert issues[0]["field"] == "示例 1 原文"
    assert issues[0]["match_type"] == "long_text"


def test_ignores_common_short_phrases_and_short_row_numbers() -> None:
    taxonomy = _taxonomy(
        examples=[
            {
                "text": "fit at least one size smaller",
                "explanation": "r1 属于普通表格行号",
            }
        ]
    )

    issues = find_taxonomy_sample_leaks(
        taxonomy,
        [_sample("r1", "These fit at least one size smaller than expected.")],
    )

    assert issues == []


def test_create_run_rejects_leak_before_persisting_validation() -> None:
    comment = (
        "Touchscreen taps work for quick actions, but typing a longer message is "
        "awkward because the insulated fingertips reduce precision."
    )
    taxonomy = _taxonomy(
        examples=[
            {
                "text": comment,
                "explanation": "用于说明触屏表现",
            }
        ]
    )
    draft = {
        "id": "draft-1",
        "revision": 3,
        "validation": {"blocking": []},
        "snapshot": {"taxonomy": taxonomy},
    }

    class StandardService:
        @staticmethod
        def get_draft(draft_id: str) -> dict[str, Any]:
            assert draft_id == "draft-1"
            return draft

    service = ClassificationStandardValidationService(
        database=None,  # type: ignore[arg-type]
        standard_service=StandardService(),  # type: ignore[arg-type]
        runner=None,  # type: ignore[arg-type]
    )
    service._validation_source_context = lambda *_args: (  # type: ignore[method-assign]
        {"result": {}},
        [_sample("review-1234-abcd", comment)],
        "source-1",
    )

    with pytest.raises(ValueError, match="数据泄漏") as exc_info:
        service.create_run("draft-1", 3, "source-1", 20, "user-1")

    message = str(exc_info.value)
    assert "佩戴舒适" in message
    assert "示例 1 原文" in message
    assert "review-1234-abcd" in message
    assert "改用独立编写的通用示例" in message


def test_leak_message_caps_details_but_keeps_total() -> None:
    issues = [
        {
            "label_code": f"LABEL_{index}",
            "label_name": f"标签 {index}",
            "field": "示例 1 原文",
            "review_id": f"review-{index:08d}",
            "match_type": "long_text",
        }
        for index in range(10)
    ]

    message = format_taxonomy_sample_leaks(issues)

    assert "另有 2 个标签/样本组合" in message
    assert "标签 7" in message
    assert "标签 8" not in message
