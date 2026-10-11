from model_client_helpers import _payload

from return_semantics.model_client import (
    normalize_model_payload,
)
from return_semantics.schemas import ModelClassification


def test_normalizes_unknown_semantic_text_field() -> None:
    payload = _payload([{"text": "Don't like", "reason": "没有说明具体对象"}])

    result = ModelClassification.model_validate(normalize_model_payload(payload))

    assert result.unknown_semantics[0].opinion == "Don't like"
    assert result.unknown_semantics[0].evidence == "Don't like"


def test_normalizes_unknown_semantic_string() -> None:
    payload = _payload(["Found same for 1/3 less"])

    result = ModelClassification.model_validate(normalize_model_payload(payload))

    assert result.unknown_semantics[0].evidence == "Found same for 1/3 less"


def test_moves_semantic_unit_out_of_unknown_list() -> None:
    unit = {
        "subject": "PRODUCT",
        "label_code": "OTHER_NOT_AS_EXPECTED",
        "opinion": "不符合预期",
        "sentiment": "NEGATIVE",
        "assertion": "AFFIRMED",
        "part": "UNSPECIFIED",
        "evidence": "not as expected",
        "implicit": False,
        "claim_relation": "NONE",
        "claim_id": None,
    }

    result = ModelClassification.model_validate(
        normalize_model_payload(_payload([unit]))
    )

    assert result.unknown_semantics == []
    assert result.semantic_units[0].label_code == "OTHER_NOT_AS_EXPECTED"


def test_strips_semantic_fields_from_unknown_item() -> None:
    item = {
        "subject": "PRODUCT",
        "opinion": "颜色不喜欢",
        "sentiment": "NEGATIVE",
        "assertion": "AFFIRMED",
        "part": "UNSPECIFIED",
        "evidence": "color is not preferable",
        "implicit": False,
        "claim_relation": "NONE",
        "claim_id": None,
    }

    result = ModelClassification.model_validate(
        normalize_model_payload(_payload([item]))
    )

    assert result.unknown_semantics[0].opinion == "颜色不喜欢"
    assert result.unknown_semantics[0].evidence == "color is not preferable"


def test_normalizes_unknown_semantic_description() -> None:
    item = {
        "description": "处于两个尺码之间",
        "evidence": "just in between sizes",
    }

    result = ModelClassification.model_validate(
        normalize_model_payload(_payload([item]))
    )

    assert result.unknown_semantics[0].opinion == "处于两个尺码之间"
    assert result.unknown_semantics[0].evidence == "just in between sizes"


def test_unknown_semantics_with_null_code_stays_unknown():
    payload = _payload(
        [
            {
                "label_code": None,
                "opinion": "轻便",
                "evidence": "lightweight",
                "reason": "缺少适用标签",
                "sentiment": "POSITIVE",
            }
        ]
    )
    result = ModelClassification.model_validate(normalize_model_payload(payload))
    assert result.semantic_units == []
    assert result.unknown_semantics[0].evidence == "lightweight"
    assert result.unknown_semantics[0].reason == "缺少适用标签"
