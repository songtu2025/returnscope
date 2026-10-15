"""当前人工补录语义的原文证据、标签约束。"""

import pytest

from web_backend.review_batches.semantic_validation import _ReviewSemanticValidation


@pytest.mark.parametrize("evidence", ["ALPHA", "alpha", "ALPHA   beta", "ALPHA\n beta"])
def test_manual_semantic_evidence_accepts_normalized_original_text(evidence):
    _ReviewSemanticValidation()._validate_added_semantic_items(
        [{"label_code": "VALID", "evidence_text": evidence}], "ALPHA\n beta", {"VALID"}
    )


@pytest.mark.parametrize(
    "item,message",
    [
        ({"label_code": "OTHER", "evidence_text": "ALPHA"}, "标签"),
        ({"label_code": "VALID", "evidence_text": "missing"}, "当前用户反馈"),
    ],
)
def test_manual_semantic_validation_rejects_foreign_label_and_evidence(item, message):
    with pytest.raises(ValueError, match=message):
        _ReviewSemanticValidation()._validate_added_semantic_items(
            [item], "ALPHA beta", {"VALID"}
        )
