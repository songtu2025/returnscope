from __future__ import annotations

import sqlite3

import pytest

from web_backend.dashboard_insight_overview import InsightQueryScope
from web_backend.dashboard_insights import _collect_filter_options


@pytest.mark.parametrize("reuse_records", [False, True])
def test_filter_options_share_scope_and_keep_independent_values(
    reuse_records: bool,
) -> None:
    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(
            "CREATE TABLE classification_result_records "
            "(listing TEXT, product_name TEXT, product_sku TEXT, included INTEGER)"
        )
        connection.executemany(
            "INSERT INTO classification_result_records VALUES (?, ?, ?, ?)",
            [
                ("L2", "zeta", "sku-b", 1),
                ("L1", "Alpha", "sku-a", 1),
                ("L1", "Alpha", "sku-b", 1),
                (None, " ", "", 1),
                ("", None, None, 1),
                ("outside", "Excluded", "sku-c", 0),
            ],
        )
        connection.execute(
            "CREATE TEMP TABLE dashboard_insight_records AS "
            "SELECT listing, product_name, product_sku "
            "FROM classification_result_records WHERE included = 1"
        )
        scope = InsightQueryScope(
            connection=connection,
            context={},
            where_sql="1=1",
            params=[],
            option_where="r.included = ?",
            option_params=[1],
            unit_rollup=False,
            clean_group="",
            clean_subject="",
            requested_problem="",
            report_mode=False,
            records_table="dashboard_insight_records",
        )
        connection.commit()
        statements: list[str] = []
        connection.set_trace_callback(statements.append)
        options = _collect_filter_options(scope, reuse_records)

    assert options == {
        "listings": ["L1", "L2"],
        "product_names": ["Alpha", "zeta"],
        "product_skus": ["sku-a", "sku-b"],
    }
    assert len(statements) == 1
