from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import replace

import pytest

from return_semantics.schemas import TaxonomyConfig
from web_backend.classification_unit_semantics import (
    SEMANTIC_SCHEMA,
    refresh_unit_semantics,
)
from web_backend.dashboard_insight_overview import (
    InsightQueryScope,
    _collect_semantic_breakdown,
    prepare_scope_semantics,
)
from web_backend.dashboard_insight_preparation import (
    InsightOptions,
    PreparedInsightScope,
)
from web_backend.dashboard_insights import _prepare_subject_labels
from web_backend.dashboard_reason_context import _reason_rows
from web_backend.dashboards.insight_queries import collect_overview_summary


@pytest.mark.parametrize("subject", ["", "PRODUCT", "UNKNOWN"])
@pytest.mark.parametrize("group", ["", "功能", "质量"])
def test_hierarchy_uses_reason_labels_and_deduplicates_parents(subject, group):
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.row_factory = sqlite3.Row
        connection.create_function("aligned_group", 3, lambda name, *_: name)
        connection.executescript("""
            CREATE TABLE classification_result_records (
                id TEXT, result_version_id TEXT, classification_key TEXT, listing TEXT
            );
            CREATE TABLE classification_unit_labels (
                result_version_id TEXT, classification_key TEXT,
                label_kind TEXT, label_code TEXT, label_name TEXT, label_group TEXT
            );
            INSERT INTO classification_result_records VALUES
                ('a', 'v1', 'u1', 'L1'), ('b', 'v1', 'u2', 'L1'),
                ('outside', 'v1', 'u1', 'L2');
            INSERT INTO classification_unit_labels VALUES
                ('v1', 'u1', 'problem', 'COLD', '不保暖', '功能'),
                ('v1', 'u1', 'problem', 'HOT', '过热', '功能'),
                ('v1', 'u1', 'problem', 'FAULT', '损坏', '质量'),
                ('v1', 'u2', 'problem', 'COLD', '不保暖', '功能');
            CREATE TEMP TABLE dashboard_insight_subject_labels (
                result_version_id TEXT, classification_key TEXT, label_code TEXT
            );
        """)
        subject_codes = {"PRODUCT": ["COLD", "HOT"], "UNKNOWN": ["FAULT"]}
        for key in ["u1", "u2"]:
            connection.executemany(
                "INSERT INTO dashboard_insight_subject_labels VALUES ('v1', ?, ?)",
                [(key, code) for code in subject_codes.get(subject, [])],
            )
        taxonomy = TaxonomyConfig.model_validate(
            {
                "version": "测试-v2",
                "structure_version": 2,
                "agent_family": "gloves",
                "product_context": "手套",
                "categories": [
                    {"code": "FUNCTION", "name": "功能"},
                    {"code": "WARMTH", "name": "保暖性", "parent_code": "FUNCTION"},
                    {"code": "QUALITY", "name": "质量"},
                ],
                "labels": [
                    {
                        "code": code,
                        "name": name,
                        "description": "合成测试原因",
                        "parent_code": parent,
                        "allowed_sentiments": ["NEGATIVE"],
                    }
                    for code, name, parent in [
                        ("COLD", "不保暖", "WARMTH"),
                        ("HOT", "过热", "WARMTH"),
                        ("FAULT", "损坏", "QUALITY"),
                    ]
                ],
                "validation_rules": {"allowed_groups": ["功能", "质量"]},
            }
        )
        scope = InsightQueryScope(
            connection=connection,
            context={},
            where_sql="r.listing = ?",
            params=["L1"],
            option_where="r.listing = ?",
            option_params=["L1"],
            unit_rollup=False,
            clean_group=group,
            clean_subject=subject,
            requested_problem="",
            report_mode=True,
        )
        prepared = PreparedInsightScope(scope, taxonomy, False, "", [], "", [], "", [])
        context = {
            "summary": {
                "comment_count": 2,
                "total_comment_count": 2,
                "pending_review_comment_count": 0,
                "comment_statuses": [],
            }
        }
        _, hierarchy = collect_overview_summary(
            prepared, context, InsightOptions(), "overview"
        )
        reasons = {
            row["value"]: row["record_count"]
            for row in _reason_rows(scope, include_primary=False)
        }
        counts = {node["value"]: node["record_count"] for node in hierarchy}
        leaves = {
            node["value"]: node["record_count"]
            for node in hierarchy
            if node["value"] in {"COLD", "HOT", "FAULT"}
        }
        assert leaves == reasons
        if "COLD" in counts:
            assert counts["COLD"] == counts["WARMTH"] == counts["FUNCTION"] == 2
        if "HOT" in counts:
            assert counts["HOT"] == 1
        if "FAULT" in counts:
            assert counts["FAULT"] == counts["QUALITY"] == 1


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
