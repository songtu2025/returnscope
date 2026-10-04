from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import replace

import pytest

from web_backend import dashboard_insight_details
from web_backend.dashboard_insight_details import collect_reason_details
from web_backend.dashboard_insight_scope import InsightQueryScope


def _seed_statistics(connection: sqlite3.Connection) -> None:
    for index in range(16):
        product = "产品A" if index < 15 else " "
        sku = "SKU-A" if index < 10 else "SKU-B" if index < 15 else " "
        key = f"key-{index}"
        connection.execute(
            "INSERT INTO classification_result_records VALUES (?, 'v1', ?, ?, ?, ?, ?)",
            (
                str(index),
                key,
                "L1" if index < 10 else "L2",
                "2026-10-01" if index < 15 else None,
                product,
                sku,
            ),
        )
        codes = ["FIT", "OTHER"] if index < 10 else ["FIT"] if index < 15 else ["OTHER"]
        for code in codes:
            connection.execute(
                "INSERT INTO classification_unit_labels "
                "VALUES ('v1', ?, 'problem', ?, ?)",
                (key, code, "偏小" if code == "FIT" else "其他原因"),
            )
        if index < 10:
            connection.execute(
                "INSERT INTO dashboard_insight_subject_labels VALUES ('v1', ?, 'FIT')",
                (key,),
            )


@pytest.fixture
def statistics_scope(monkeypatch: pytest.MonkeyPatch) -> Iterator[InsightQueryScope]:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE classification_result_records (
            id TEXT PRIMARY KEY, result_version_id TEXT, classification_key TEXT,
            listing TEXT, return_date TEXT, product_name TEXT, product_sku TEXT
        );
        CREATE TABLE classification_unit_labels (
            result_version_id TEXT, classification_key TEXT, label_kind TEXT,
            label_code TEXT, label_name TEXT
        );
        CREATE TEMP TABLE dashboard_insight_subject_labels (
            result_version_id TEXT, classification_key TEXT, label_code TEXT
        );
    """)
    _seed_statistics(connection)
    monkeypatch.setattr(
        dashboard_insight_details,
        "_collect_reason_semantics",
        lambda *args: ([], [], 0),
    )
    monkeypatch.setattr(
        dashboard_insight_details,
        "list_reason_evidence",
        lambda *args, **kwargs: {"items": []},
    )
    try:
        yield InsightQueryScope(
            connection=connection,
            context={},
            where_sql="1=1",
            params=[],
            option_where="1=1",
            option_params=[],
            unit_rollup=False,
            clean_group="",
            clean_subject="",
            requested_problem="FIT",
            report_mode=False,
        )
    finally:
        connection.close()


def test_reason_statistics_keep_rates_samples_and_query_budget(statistics_scope):
    statements: list[str] = []
    statistics_scope.connection.set_trace_callback(statements.append)
    details = collect_reason_details(
        statistics_scope,
        {"value": "FIT", "record_count": 15},
        {"total_records": 16, "label_counts": {"FIT": 15, "OTHER": 11}},
    )
    assert len(statements) == 7
    assert details["products"] == [
        {
            "value": "产品A",
            "record_count": 15,
            "total_record_count": 15,
            "reason_share": 100.0,
            "product_reason_rate": 100.0,
            "overall_reason_rate": 93.8,
            "lift": 1.07,
            "reliable": True,
        }
    ]
    assert [item["record_count"] for item in details["variants"]] == [10, 5]
    assert [item["reliable"] for item in details["variants"]] == [True, False]
    assert details["co_reasons"] == [
        {
            "value": "OTHER",
            "label": "其他原因",
            "record_count": 10,
            "percentage": 66.7,
            "baseline_record_count": 11,
            "lift": 0.97,
        }
    ]
    assert details["trend"][0]["record_count"] == 15
    assert details["trend"][0]["low_sample"] is False
    assert details["evidence_total"] == 15


@pytest.mark.parametrize("subject", ["", "PRODUCT"])
def test_reason_statistics_keep_filtered_and_subject_scopes(statistics_scope, subject):
    scope = replace(
        statistics_scope,
        where_sql="r.listing = ?",
        params=["L2"],
        clean_subject=subject,
    )
    count = 0 if subject else 5
    details = collect_reason_details(
        scope,
        {"value": "FIT", "record_count": count},
        {"total_records": 6, "label_counts": {"FIT": count, "OTHER": 1}},
    )
    assert sum(item["record_count"] for item in details["products"]) == count
    assert sum(item["record_count"] for item in details["variants"]) == count
    assert details["co_reasons"] == []
    assert details["trend"][0]["low_sample"] is True


def test_reason_statistics_without_selection_does_not_query(statistics_scope):
    statements: list[str] = []
    statistics_scope.connection.set_trace_callback(statements.append)
    details = collect_reason_details(
        statistics_scope, None, {"total_records": 0, "label_counts": {}}
    )
    assert statements == []
    assert details["evidence_total"] == details["semantic_record_count"] == 0
    assert all(
        value == []
        for key, value in details.items()
        if not key.endswith(("total", "count"))
    )
