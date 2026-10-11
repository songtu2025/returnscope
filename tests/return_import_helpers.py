from __future__ import annotations

from pathlib import Path

import pandas as pd

from return_semantics.data import (
    RETURN_COLUMNS,
    RETURN_STORE_COLUMN,
)
from web_backend.dataset_service import DatasetService


def _return_row(order_id: str, comment: str) -> dict[str, str]:
    values = {column: "" for column in RETURN_COLUMNS}
    values.update(
        {
            "return-date": "2026-08-20",
            "order-id": order_id,
            "sku": "SKU-1",
            "product-name": "测试商品",
            "quantity": "1",
            "reason": "OTHER",
            "customer-comments": comment,
            RETURN_STORE_COLUMN: "SENWAYZON:US",
        }
    )
    return values


def _write_returns(path: Path, rows: list[dict[str, str]]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def _create_task_input(
    service: DatasetService,
    source: Path,
) -> dict[str, object]:
    return service.create(
        name="测试退货数据",
        kind="returns",
        description="",
        source_path=source,
        original_name=source.name,
        content_type="text/csv",
        change_note="首次导入",
        actor_id="user-1",
    )


def _database_counts(database) -> dict[str, int]:
    tables = ("datasets", "dataset_versions", "dataset_imports", "audit_logs")
    with database.connect() as connection:
        return {
            table: int(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            )
            for table in tables
        }
