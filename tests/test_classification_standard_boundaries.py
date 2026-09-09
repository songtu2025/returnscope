from copy import deepcopy

import pytest

from web_backend.classification_standard_issues import label_field_issues


def _taxonomy(required=True):
    return {
        "labels": [
            {
                "code": "BOUNDARY",
                "name": "携带/收纳方便",
                "group": "其他",
                "description": "",
                "allowed_sentiments": ["POSITIVE"],
            },
            {
                "code": "ORDINARY",
                "name": "不合身",
                "group": "尺码",
                "description": "",
                "allowed_sentiments": ["NEGATIVE"],
            },
        ],
        "validation_rules": {
            "boundary_required_labels": ["BOUNDARY"] if required else [],
        },
    }


def _add_examples(label):
    label["examples"] = [
        {
            "text": "The clip makes storage easy.",
            "applies": True,
            "sentiment": "POSITIVE",
            "explanation": "明确收纳便利。",
        },
        {
            "text": "The gloves feel lightweight.",
            "applies": False,
            "sentiment": None,
            "explanation": "只有重量评价，没有收纳评价。",
        },
    ]


def test_normal_business_leaf_needs_no_long_definition_or_examples():
    assert label_field_issues(_taxonomy(required=False)) == []


def test_only_explicit_boundary_labels_require_exclusions_and_examples():
    issues = label_field_issues(_taxonomy())
    assert len(issues) == 2
    assert {item["field"] for item in issues} == {"exclusions", "examples"}
    assert all(item["kind"] == "missing_boundary" for item in issues)
    assert all(item["label_code"] == "BOUNDARY" for item in issues)
    assert all(item["label_index"] == 0 for item in issues)


def test_complete_boundary_passes_without_description_and_does_not_mutate():
    taxonomy = _taxonomy()
    label = taxonomy["labels"][0]
    label["exclusions"] = ["只有轻便而没有收纳便利时不适用。"]
    _add_examples(label)
    before = deepcopy(taxonomy)
    assert label_field_issues(taxonomy) == []
    assert taxonomy == before


@pytest.mark.parametrize("exclusions", [[], [""], ["  "]])
def test_blank_exclusion_does_not_satisfy_boundary(exclusions):
    taxonomy = _taxonomy()
    taxonomy["labels"][0]["exclusions"] = exclusions
    _add_examples(taxonomy["labels"][0])
    assert [item["field"] for item in label_field_issues(taxonomy)] == ["exclusions"]


@pytest.mark.parametrize("missing", [True, False])
def test_both_applicable_and_inapplicable_examples_are_required(missing):
    taxonomy = _taxonomy()
    label = taxonomy["labels"][0]
    label["exclusions"] = ["不从重量推收纳。"]
    _add_examples(label)
    label["examples"] = [x for x in label["examples"] if x["applies"] is not missing]
    issues = label_field_issues(taxonomy)
    assert [item["field"] for item in issues] == ["examples"]


@pytest.mark.parametrize("field", ["text", "explanation"])
def test_blank_example_fields_do_not_satisfy_boundary(field):
    taxonomy = _taxonomy()
    label = taxonomy["labels"][0]
    label["exclusions"] = ["不从重量推收纳。"]
    _add_examples(label)
    label["examples"][0][field] = "  "
    assert [item["field"] for item in label_field_issues(taxonomy)] == ["examples"]


def test_existing_required_fields_still_report_their_own_issue():
    taxonomy = _taxonomy(required=False)
    taxonomy["labels"][1]["allowed_sentiments"] = []
    issues = label_field_issues(taxonomy)
    assert len(issues) == 1
    assert issues[0]["kind"] == "missing_sentiment"
    assert issues[0]["label_code"] == "ORDINARY"
