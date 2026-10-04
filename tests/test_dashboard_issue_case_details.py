from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing

import pytest

from web_backend.dashboard_issue_case_details import populate_issue_case_details
from web_backend.dashboards.issue_case_detail_statistics import (
    collect_case_co_reasons,
    collect_case_trend,
)
from web_backend.dashboards.issue_case_semantics import collect_case_semantics

CASE_WHERE = (
    "r.result_version_id = ? AND TRIM(r.product_name) = ? AND TRIM(r.product_sku) = ?"
)
CASE_PARAMS = ("version", "合成商品", "SKU-A")


@pytest.fixture
def case_connection() -> Iterator[sqlite3.Connection]:
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.row_factory = sqlite3.Row
        connection.executescript(
            """
            CREATE TABLE classification_result_records(
                id, result_version_id, classification_key, product_name,
                product_sku, return_date, comment, reason
            );
            CREATE TABLE classification_unit_labels(
                result_version_id, classification_key, label_kind, label_code,
                label_name
            );
            CREATE TABLE classification_units(
                result_version_id, classification_key, classification_json
            );
            """
        )
        records = [
            ("a", "SKU-A", "2026-01-04"),
            ("b", "SKU-A", "2026-01-05"),
            ("c", "SKU-A", "2026-01-06"),
            ("d", "SKU-A", None),
            ("e", "SKU-B", "2026-01-05"),
        ]
        connection.executemany(
            "INSERT INTO classification_result_records VALUES "
            "(?, 'version', ?, ' 合成商品 ', ?, ?, '合成意见', '合成原因')",
            [(key, key, sku, date) for key, sku, date in records],
        )
        connection.executemany(
            "INSERT INTO classification_unit_labels VALUES "
            "('version', ?, 'problem', ?, ?)",
            [(key, "FIT", "偏小") for key in ["a", "b", "c", "e"]]
            + [(key, "OTHER", "伴随原因") for key in ["a", "a", "b", "d"]],
        )
        _seed_case_semantics(connection)
        yield connection


def _seed_case_semantics(connection: sqlite3.Connection) -> None:
    values = {
        "a": [("SOLE", "硬", "证据乙"), ("SOLE", "硬", "证据甲")],
        "b": [("unspecified", "紧", None)],
        "c": [("", None, None)],
        "e": [("TOE", "其他变体意见", "其他变体证据")],
    }
    for key, facts in values.items():
        units = [
            {
                "label_code": "FIT",
                "part": part,
                "opinion": opinion,
                "evidence": evidence,
            }
            for part, opinion, evidence in facts
        ]
        connection.execute(
            "INSERT INTO classification_units VALUES ('version', ?, ?)",
            (key, json.dumps({"semantic_units": units}, ensure_ascii=False)),
        )


def test_case_trend_keeps_monday_weeks_variant_scope_and_missing_dates(case_connection):
    trend = collect_case_trend(case_connection, "FIT", CASE_WHERE, CASE_PARAMS)
    assert [(row["period_start"], row["period_end"]) for row in trend] == [
        ("2025-12-29", "2026-01-04"),
        ("2026-01-05", "2026-01-11"),
    ]
    assert [row["record_count"] for row in trend] == [1, 2]
    assert [row["total_record_count"] for row in trend] == [1, 2]
    assert all(row["percentage"] == 100.0 and row["low_sample"] for row in trend)


def test_case_companions_count_distinct_records_in_case_scope(case_connection):
    assert collect_case_co_reasons(
        case_connection, {"record_count": 3}, "FIT", CASE_WHERE, CASE_PARAMS
    ) == [
        {"value": "OTHER", "label": "伴随原因", "record_count": 2, "percentage": 66.7}
    ]


def test_case_semantics_keeps_record_coverage_raw_parts_and_representative_evidence(
    case_connection,
):
    profile = collect_case_semantics(
        case_connection, {"record_count": 3}, "FIT", CASE_WHERE, CASE_PARAMS
    )
    assert profile["record_count"] == 3
    assert profile["coverage"] == 100.0
    assert profile["specified_part_record_count"] == 1
    assert profile["specified_part_coverage"] == 33.3
    # 原查询按 json_each 的语义单元分组，保留不同证据下的重复部位。
    assert [(row["value"], row["record_count"]) for row in profile["parts"]] == [
        ("SOLE", 1),
        ("SOLE", 1),
        ("UNSPECIFIED", 1),
        ("unspecified", 1),
    ]
    assert [row["percentage"] for row in profile["parts"]] == [33.3] * 4
    opinions = {row["opinion"]: row for row in profile["opinions"]}
    assert opinions["硬"]["record_count"] == 1
    assert opinions["硬"]["evidence"] == min("证据甲", "证据乙")
    assert opinions["紧"]["evidence"] is None
    assert opinions["紧"]["subject"] is None
    assert "其他变体意见" not in opinions


def test_case_without_semantics_has_zero_coverage_and_empty_profile(case_connection):
    assert collect_case_semantics(
        case_connection, {"record_count": 2}, "OTHER", CASE_WHERE, CASE_PARAMS
    ) == {
        "record_count": 0,
        "coverage": 0.0,
        "specified_part_record_count": 0,
        "specified_part_coverage": 0.0,
        "parts": [],
        "opinions": [],
    }


def test_case_details_updates_existing_case_and_returns_same_list(case_connection):
    case = {
        "reason_code": "FIT",
        "product_name": "合成商品",
        "product_sku": "SKU-A",
        "record_count": 3,
    }
    cases = [case]
    returned = populate_issue_case_details(
        case_connection, cases, "r.result_version_id = ?", ["version"]
    )
    assert returned is cases and returned[0] is case
    assert list(case)[-4:] == ["trend", "co_reasons", "semantic_profile", "samples"]
    assert case["samples"][0]["classification_key"] == "a"
    assert case["samples"][0]["has_specific_part"] is True
    assert case["semantic_profile"]["coverage"] == 100.0


def test_empty_case_details_does_not_query_database():
    cases = []
    with closing(sqlite3.connect(":memory:")) as connection:
        assert populate_issue_case_details(connection, cases, "unused", []) is cases
