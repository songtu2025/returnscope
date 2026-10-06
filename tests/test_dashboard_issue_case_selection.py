from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from web_backend.dashboard_issue_cases import list_issue_cases
from web_backend.dashboards.issue_case_selection import select_issue_cases
from web_backend.database import Database


def _candidate_rows(values: list[tuple[str, str, int, int]]) -> list[sqlite3.Row]:
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(
            "CREATE TABLE candidates(label_code, product_name, product_sku, "
            "record_count, total_record_count)"
        )
        connection.executemany(
            "INSERT INTO candidates VALUES (?, '合成商品', ?, ?, ?)", values
        )
        return connection.execute("SELECT * FROM candidates").fetchall()


@pytest.mark.parametrize(
    "count,total,baseline",
    [
        (9, 10, 10),
        (9, 9, 10),
        (10, 20, 50),
        (10, 10, 100),
    ],
)
def test_case_selection_excludes_small_or_unconcentrated_samples(
    count, total, baseline
):
    rows = _candidate_rows([("FIT", "SKU", count, total)])
    assert (
        select_issue_cases(
            rows,
            {"FIT": {"label": "偏小", "label_group": "适配", "record_count": baseline}},
            ["FIT"],
            100,
            3,
        )
        == []
    )


def test_case_selection_keeps_metrics_stable_id_and_reason_order():
    rows = _candidate_rows(
        [
            ("FIT", "A", 11, 19),
            ("FIT", "Z", 11, 19),
            ("OTHER", "B", 10, 12),
            ("MISSING", "C", 10, 12),
        ]
    )
    baselines = {
        "FIT": {"label": "偏小", "label_group": "适配", "record_count": 11},
        "OTHER": {"label": "其他", "label_group": "其他", "record_count": 10},
    }
    cases = select_issue_cases(rows, baselines, ["OTHER", "FIT"], 39, 1)
    assert [case["reason_code"] for case in cases] == ["OTHER", "FIT"]
    assert cases[1]["product_sku"] == "Z"
    assert cases[1]["record_count"] == 11
    assert cases[1]["total_record_count"] == 19
    assert cases[1]["issue_rate"] == 57.9
    assert cases[1]["overall_rate"] == 28.2
    assert cases[1]["lift"] == 2.05
    assert cases[1]["excess_record_count"] == 6
    assert cases[1]["reliable"] is True
    repeated = select_issue_cases(rows, baselines, ["OTHER", "FIT"], 39, 2)
    assert cases[1]["id"] == repeated[1]["id"]
    assert [case["product_sku"] for case in repeated[1:]] == ["Z", "A"]


@pytest.mark.parametrize("maximum", [0, -1, 11])
def test_case_limit_is_validated_before_loading_dashboard(tmp_path: Path, maximum):
    database = Database(tmp_path / "absent.db")
    with pytest.raises(ValueError, match="每个问题的案例数量必须在 1 到 10 之间"):
        list_issue_cases(
            database, "missing", "missing", ["FIT"], max_cases_per_reason=maximum
        )
    assert not database.path.exists()


def test_empty_reason_codes_return_before_case_limit_validation(tmp_path: Path):
    database = Database(tmp_path / "absent.db")
    assert (
        list_issue_cases(
            database, "missing", "missing", ["", " "], max_cases_per_reason=0
        )
        == []
    )
    assert not database.path.exists()


@pytest.mark.parametrize(
    "count,total,baseline,expected_lift",
    [
        (11, 20, 51, None),
        (11, 20, 50, 1.1),
        (12, 20, 50, 1.2),
        (10, 10, 50, 2.0),
    ],
)
def test_case_selection_preserves_exact_lift_and_sample_boundaries(
    count, total, baseline, expected_lift
):
    rows = _candidate_rows([("FIT", "SKU", count, total)])
    cases = select_issue_cases(
        rows,
        {"FIT": {"label": "偏小", "label_group": "适配", "record_count": baseline}},
        ["FIT"],
        100,
        3,
    )
    if expected_lift is None:
        assert cases == []
    else:
        assert len(cases) == 1
        assert cases[0]["lift"] == expected_lift
        assert cases[0]["record_count"] == count
        assert cases[0]["total_record_count"] == total
