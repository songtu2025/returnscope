from __future__ import annotations

import json
import sqlite3
from contextlib import closing

import pytest

from web_backend import dashboard_insight_details
from web_backend.dashboard_insight_details import collect_reason_details
from web_backend.dashboard_insight_overview import InsightQueryScope


@pytest.mark.parametrize("subject", ["", "PRODUCT", "UNKNOWN"])
@pytest.mark.parametrize("listing", ["", "L1", "L2"])
def test_semantics_keep_record_scope_and_separate_result_versions(
    subject: str, listing: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 两个版本使用相同分类键，重复语义、对象和反馈范围均须独立统计。
    records = [
        ("a1", "v1", "shared", "L1"),
        ("a2", "v1", "shared", "L1"),
        ("a3", "v1", "shared", "L2"),
        ("b1", "v2", "shared", "L1"),
        ("b2", "v2", "shared", "L2"),
        ("c1", "v1", "other", "L1"),
    ]
    units = [
        (
            "v1",
            "shared",
            [
                ("PRODUCT", "WHOLE_SHOE", "tight", "a"),
                ("PRODUCT", "WHOLE_SHOE", "tight", "z"),
                ("UNKNOWN", "", "maybe", "u"),
            ],
        ),
        ("v2", "shared", [("PRODUCT", "TOE_BOX", "large", "b")]),
        ("v1", "other", []),
    ]
    monkeypatch.setattr(
        dashboard_insight_details,
        "list_reason_evidence",
        lambda *args, **kwargs: {"items": []},
    )
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.row_factory = sqlite3.Row
        opinion_reads = 0

        def extract_semantic(value: str, path: str):
            nonlocal opinion_reads
            if path == "$.opinion":
                opinion_reads += 1
            return json.loads(value).get(path[2:])

        connection.create_function("json_extract", 2, extract_semantic)
        connection.executescript("""
            CREATE TABLE classification_result_records (
                id TEXT PRIMARY KEY, result_version_id TEXT, classification_key TEXT,
                listing TEXT, return_date TEXT, product_name TEXT, product_sku TEXT
            );
            CREATE TABLE classification_units (
                result_version_id TEXT, classification_key TEXT, classification_json TEXT,
                PRIMARY KEY (result_version_id, classification_key)
            );
            CREATE TABLE classification_unit_labels (
                result_version_id TEXT, classification_key TEXT, label_kind TEXT,
                label_code TEXT, label_name TEXT
            );
            CREATE TEMP TABLE dashboard_insight_subject_labels (
                id TEXT, label_code TEXT, PRIMARY KEY (id, label_code)
            );
        """)
        connection.executemany(
            "INSERT INTO classification_result_records VALUES (?, ?, ?, ?, '2026-08-01', '鞋', 'SKU')",
            records,
        )
        for version, key, semantics in units:
            connection.execute(
                "INSERT INTO classification_units VALUES (?, ?, ?)",
                (
                    version,
                    key,
                    json.dumps(
                        {
                            "semantic_units": [
                                {
                                    "label_code": "FIT",
                                    "subject": owner,
                                    "part": part,
                                    "opinion": opinion,
                                    "evidence": evidence,
                                }
                                for owner, part, opinion, evidence in semantics
                            ]
                        }
                    ),
                ),
            )
            connection.execute(
                "INSERT INTO classification_unit_labels VALUES (?, ?, 'problem', ?, '原因')",
                (version, key, "FIT" if semantics else "OTHER"),
            )
            connection.executemany(
                "INSERT INTO dashboard_insight_subject_labels VALUES (?, 'FIT')",
                [
                    (record[0],)
                    for record in records
                    if record[1:3] == (version, key)
                    and any(owner == subject for owner, *_ in semantics)
                ],
            )
        scope = InsightQueryScope(
            connection=connection,
            context={},
            where_sql="r.listing = ?" if listing else "1=1",
            params=[listing] if listing else [],
            option_where="1=1",
            option_params=[],
            unit_rollup=False,
            clean_group="",
            clean_subject=subject,
            requested_problem="FIT",
            report_mode=False,
        )
        first_count = sum(
            record[1] == "v1"
            and record[2] == "shared"
            and (not listing or record[3] == listing)
            for record in records
        )
        second_count = sum(
            record[1] == "v2" and (not listing or record[3] == listing)
            for record in records
        )
        count = first_count + (0 if subject == "UNKNOWN" else second_count)
        result = collect_reason_details(
            scope,
            {"value": "FIT", "record_count": count},
            {"total_records": len(records), "label_counts": {"FIT": count}},
        )

    expected_parts = {}
    expected_opinions = set()
    if subject != "UNKNOWN":
        expected_parts.update(WHOLE_SHOE=first_count, TOE_BOX=second_count)
        expected_opinions.update(
            {
                ("tight", "WHOLE_SHOE", first_count, "z"),
                ("large", "TOE_BOX", second_count, "b"),
            }
        )
    if subject != "PRODUCT":
        expected_parts["UNSPECIFIED"] = first_count
        expected_opinions.add(("maybe", "UNSPECIFIED", first_count, "u"))
    assert result["semantic_record_count"] == count
    # 意见解析次数由语义单元数量决定，不能随反馈记录或聚合查询倍增。
    assert opinion_reads <= 4
    assert {
        item["value"]: item["record_count"] for item in result["semantic_parts"]
    } == expected_parts
    assert {
        (item["opinion"], item["part"], item["record_count"], item["evidence"])
        for item in result["semantic_opinions"]
    } == expected_opinions
