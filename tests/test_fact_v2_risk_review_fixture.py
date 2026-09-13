from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.build_fact_v2_risk_review_fixture import convert_fixture
from web_backend.classification_standard_validation_service import (
    ClassificationStandardValidationService,
)

ROOT = Path(__file__).parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "fact_v2_model_risk_cases.json"
TAXONOMY_PATH = ROOT / "config" / "taxonomy_gloves.json"
SCRIPT_PATH = ROOT / "scripts" / "build_fact_v2_risk_review_fixture.py"


def _contract() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _parse_with_validation_service(
    path: Path, monkeypatch: Any
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    monkeypatch.setattr(
        ClassificationStandardValidationService,
        "_published_config_id",
        lambda self: "config-test",
    )
    service = object.__new__(ClassificationStandardValidationService)
    taxonomy = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    draft = {
        "is_new": False,
        "standard_key": "gloves",
        "snapshot": {
            "taxonomy": taxonomy,
            "variants": [
                {
                    "category_a": "手套",
                    "category_b": "滑雪手套",
                    "attributes": {},
                }
            ],
            "model_policy": {"version": "test-model-policy"},
        },
    }
    return service._review_source_context(
        path.name,
        path.read_bytes(),
        draft,
        sample_size=20,
    )


def test_workbook_is_consumed_by_existing_validation_service(
    tmp_path: Path, monkeypatch: Any
) -> None:
    output_path = tmp_path / "fact-v2-risk-review.xlsx"
    convert_fixture(FIXTURE_PATH, output_path)

    source, samples = _parse_with_validation_service(output_path, monkeypatch)
    cases = _contract()["cases"]
    cases_by_id = {case["case_id"]: case for case in cases}
    samples_by_id = {sample["review_id"]: sample for sample in samples}

    assert source["kind"] == "review_file"
    assert source["result"]["analysis_context"] == "review"
    assert source["result"]["available_sample_count"] == len(cases)
    assert len(samples) == len(cases)
    assert set(samples_by_id) == set(cases_by_id)

    for case_id, sample in samples_by_id.items():
        case = cases_by_id[case_id]
        assert sample["comment"] == case["comment"]
        assert sample["source_category"] == "手套"
        assert sample["listing"] == case["risk_type"]


def test_reference_facts_survive_existing_importer(
    tmp_path: Path, monkeypatch: Any
) -> None:
    output_path = tmp_path / "fact-v2-risk-reference.xlsx"
    convert_fixture(FIXTURE_PATH, output_path)
    _, samples = _parse_with_validation_service(output_path, monkeypatch)
    samples_by_id = {sample["review_id"]: sample for sample in samples}

    for case in _contract()["cases"]:
        reference = samples_by_id[case["case_id"]]["reference"]
        expected_facts = case["expected_facts"]
        assert reference["fact_state_complete"] is True
        assert reference["facts"] == [
            {
                "expected_statement_type": fact["statement_type"],
                "expected_actor_ref": "",
                "expected_product_ref": fact["product_ref"],
                "expected_condition": [fact["condition"]],
                "evidence": fact["evidence"],
                "label_codes": (
                    [fact["required_label_code"]] if fact["required_label_code"] else []
                ),
            }
            for fact in expected_facts
        ]
        assert reference["units"] == [
            {
                "label_code": fact["required_label_code"],
                "sentiment": fact["sentiment"],
                "part": "UNSPECIFIED",
                "evidence": fact["evidence"],
            }
            for fact in expected_facts
            if fact["required_label_code"]
        ]


def test_repeated_conversion_has_identical_parsed_content(
    tmp_path: Path, monkeypatch: Any
) -> None:
    first_path = tmp_path / "first.xlsx"
    second_path = tmp_path / "second.xlsx"
    convert_fixture(FIXTURE_PATH, first_path)
    convert_fixture(FIXTURE_PATH, second_path)

    _, first_samples = _parse_with_validation_service(first_path, monkeypatch)
    _, second_samples = _parse_with_validation_service(second_path, monkeypatch)

    assert first_samples == second_samples


def test_cli_writes_valid_review_workbook(tmp_path: Path, monkeypatch: Any) -> None:
    output_path = tmp_path / "cli" / "fact-v2-risk-review.xlsx"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(FIXTURE_PATH), str(output_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert output_path.is_file()
    _, samples = _parse_with_validation_service(output_path, monkeypatch)
    assert len(samples) == len(_contract()["cases"])
