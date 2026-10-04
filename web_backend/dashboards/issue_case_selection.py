from __future__ import annotations

import hashlib
import sqlite3
from typing import Any

from web_backend.dashboard_support import percentage


def _eligible_case(
    row: sqlite3.Row,
    overall: dict[str, Any],
    total_record_count: int,
) -> dict[str, Any] | None:
    code = str(row["label_code"])
    record_count = int(row["record_count"])
    variant_total = int(row["total_record_count"])
    baseline = overall["record_count"] / total_record_count
    lift = round((record_count / variant_total) / baseline, 2)
    excess = round(record_count - variant_total * baseline)
    if variant_total < 10 or record_count < 10 or lift < 1.1 or excess <= 0:
        return None
    product_name = str(row["product_name"])
    product_sku = str(row["product_sku"])
    identity = f"{code}\x1f{product_name}\x1f{product_sku}"
    return {
        "id": (
            f"issue_case.{code}."
            f"{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:12]}"
        ),
        "reason_code": code,
        "label": overall["label"],
        "label_group": overall["label_group"],
        "product_name": product_name,
        "product_sku": product_sku,
        "record_count": record_count,
        "total_record_count": variant_total,
        "reason_record_count": overall["record_count"],
        "reason_share": percentage(
            record_count,
            overall["record_count"],
        ),
        "issue_rate": percentage(
            record_count,
            variant_total,
        ),
        "overall_rate": percentage(
            overall["record_count"],
            total_record_count,
        ),
        "lift": lift,
        "excess_record_count": excess,
        "reliable": True,
    }


def select_issue_cases(
    candidate_rows: list[sqlite3.Row],
    overall_by_code: dict[str, dict[str, Any]],
    clean_codes: list[str],
    total_record_count: int,
    max_cases_per_reason: int,
) -> list[dict[str, Any]]:
    cases_by_code: dict[str, list[dict[str, Any]]] = {code: [] for code in clean_codes}
    for row in candidate_rows:
        code = str(row["label_code"])
        overall = overall_by_code.get(code)
        if overall is None:
            continue
        case = _eligible_case(row, overall, total_record_count)
        if case is not None:
            cases_by_code[code].append(case)
    selected_cases: list[dict[str, Any]] = []
    for code in clean_codes:
        ranked = sorted(
            cases_by_code[code],
            key=lambda item: (
                int(item["excess_record_count"]),
                float(item["lift"]),
                int(item["record_count"]),
                str(item["product_name"]),
                str(item["product_sku"]),
            ),
            reverse=True,
        )
        selected_cases.extend(ranked[:max_cases_per_reason])
    return selected_cases
