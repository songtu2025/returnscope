from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import replace

from web_backend.classification_unit_semantics import (
    SEMANTIC_SCHEMA,
    refresh_unit_semantics,
)
from web_backend.dashboard_insight_overview import (
    InsightQueryScope,
    _collect_semantic_breakdown,
    prepare_scope_semantics,
)
from web_backend.dashboard_insights import _prepare_subject_labels


def test_shared_semantics_keep_scope_weights_and_version_keys() -> None:
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.row_factory = sqlite3.Row
        reads = 0

        def extract_semantic(value: str, path: str):
            nonlocal reads
            reads += 1
            return json.loads(value).get(path[2:])

        connection.create_function("json_extract", 2, extract_semantic)
        connection.executescript("""
            CREATE TABLE classification_result_records (
                result_version_id TEXT, classification_key TEXT, listing TEXT
            );
            CREATE TABLE classification_units (
                result_version_id TEXT, classification_key TEXT, classification_json TEXT,
                PRIMARY KEY (result_version_id, classification_key)
            );
            CREATE TABLE classification_unit_labels (
                result_version_id TEXT, classification_key TEXT,
                label_kind TEXT, label_code TEXT
            );
            INSERT INTO classification_result_records VALUES
                ('v1', 'shared', 'L1'), ('v1', 'shared', 'L1'),
                ('v1', 'shared', 'L2'), ('v2', 'shared', 'L2');
            INSERT INTO classification_unit_labels VALUES
                ('v1', 'shared', 'problem', 'FIT'),
                ('v1', 'shared', 'problem', 'OTHER'),
                ('v2', 'shared', 'problem', 'LARGE');
        """)
        for version, key, semantics in [
            (
                "v1",
                "shared",
                [("PRODUCT", "FIT"), ("PRODUCT", "FIT"), ("UNKNOWN", "OTHER")],
            ),
            ("v2", "shared", [("PRODUCT", "LARGE")]),
            ("v1", "outside", [("UNKNOWN", "OTHER")]),
        ]:
            connection.execute(
                "INSERT INTO classification_units VALUES (?, ?, ?)",
                (
                    version,
                    key,
                    json.dumps(
                        {
                            "semantic_units": [
                                {"subject": subject, "label_code": code}
                                for subject, code in semantics
                            ]
                        }
                    ),
                ),
            )
        connection.execute(SEMANTIC_SCHEMA)
        refresh_unit_semantics(connection)
        reads = 0
        scope = InsightQueryScope(
            connection=connection,
            context={},
            where_sql="1=1",
            params=[],
            option_where="1=1",
            option_params=[],
            unit_rollup=False,
            clean_group="",
            clean_subject="",
            requested_problem="",
            report_mode=False,
        )
        prepare_scope_semantics(connection, scope.where_sql, scope.params)
        parsed_reads = reads
        base, base_reasons = _collect_semantic_breakdown(scope, 4)
        narrowed, narrowed_reasons = _collect_semantic_breakdown(
            replace(scope, where_sql="r.listing = ?", params=["L2"]), 2
        )
        connection.execute("""
            CREATE TEMP TABLE dashboard_insight_weighted_units AS
            SELECT result_version_id, classification_key, COUNT(*) AS record_count
            FROM classification_result_records
            GROUP BY result_version_id, classification_key
        """)
        weighted, weighted_reasons = _collect_semantic_breakdown(
            replace(scope, records_table="dashboard_insight_weighted_units"), 4
        )
        assert (weighted, weighted_reasons) == (base, base_reasons)
        assert reads == parsed_reads == 0
        assert {
            item["value"]: (
                item["record_count"],
                item["semantic_unit_count"],
                item["percentage"],
            )
            for item in base
        } == {"PRODUCT": (4, 7, 100.0), "UNKNOWN": (3, 3, 75.0)}
        assert {
            item["value"]: (
                item["record_count"],
                item["semantic_unit_count"],
                item["percentage"],
            )
            for item in narrowed
        } == {"PRODUCT": (2, 3, 100.0), "UNKNOWN": (1, 1, 50.0)}
        assert (
            base_reasons
            == narrowed_reasons
            == {"FIT": ["PRODUCT"], "LARGE": ["PRODUCT"], "OTHER": ["UNKNOWN"]}
        )


def test_subject_labels_keep_unit_keys_without_expanding_feedback() -> None:
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            CREATE TABLE classification_result_records (
                result_version_id TEXT, classification_key TEXT, listing TEXT
            );
            CREATE TABLE classification_units (
                result_version_id TEXT, classification_key TEXT, classification_json TEXT,
                PRIMARY KEY (result_version_id, classification_key)
            );
        """)
        connection.executemany(
            "INSERT INTO classification_result_records VALUES (?, 'shared', ?)",
            [("v1", "L1")] * 20 + [("v2", "L1")] * 10 + [("v3", "L2")],
        )
        for version, semantics in [
            ("v1", [("PRODUCT", "FIT")]),
            ("v2", [("PRODUCT", "OTHER"), ("UNKNOWN", "FIT")]),
            ("v3", [("PRODUCT", "OUTSIDE")]),
        ]:
            connection.execute(
                "INSERT INTO classification_units VALUES (?, 'shared', ?)",
                (
                    version,
                    json.dumps(
                        {
                            "semantic_units": [
                                {"subject": subject, "label_code": code}
                                for subject, code in semantics
                            ]
                            * 2
                        }
                    ),
                ),
            )
        connection.execute(SEMANTIC_SCHEMA)
        refresh_unit_semantics(connection)
        _prepare_subject_labels(connection, "r.listing = ?", ["L1"], "PRODUCT")
        rows = connection.execute(
            "SELECT * FROM dashboard_insight_subject_labels ORDER BY result_version_id"
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            ("v1", "shared", "FIT"),
            ("v2", "shared", "OTHER"),
        ]
