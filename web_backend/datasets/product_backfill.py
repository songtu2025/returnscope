"""停服升级时回填当前和历史任务引用的资料，不在在线读取中回退解析文件。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from web_backend.dataset_files import _sha256_file
from web_backend.datasets.product_store import (
    product_workbook,
    save_product_workbook,
)

if TYPE_CHECKING:
    from web_backend.database import Database


def product_sources(connection: sqlite3.Connection) -> dict[str, Path]:
    sources = {
        str(row["sha256"]): Path(row["file_path"])
        for row in connection.execute(
            "SELECT v.sha256, v.file_path FROM dataset_versions v JOIN datasets d ON d.id = v.dataset_id "
            "WHERE d.kind = 'products' AND (v.version = d.current_version "
            "OR EXISTS (SELECT 1 FROM tasks t WHERE t.product_version_id = v.id) "
            "OR EXISTS (SELECT 1 FROM classification_results r WHERE r.product_version_id = v.id))"
        )
    }
    for row in connection.execute(
        "SELECT t.snapshot_json, v.file_path FROM tasks t JOIN dataset_versions v ON v.id = t.product_version_id"
    ):
        digest = (
            json.loads(row["snapshot_json"] or "{}").get("products", {}).get("sha256")
        )
        if digest and digest not in sources:
            sources[digest] = Path(row["file_path"]).with_name(f"{digest}.xlsx")
    return sources


def backfill_product_store(database: Database) -> dict[str, int]:
    with database.connect() as connection:
        sources = product_sources(connection)
    count = 0
    rows = 0
    # 任意文件失败时，整批入库回滚；不会修改原工作簿和业务引用。
    with database.transaction(immediate=True) as connection:
        for digest, path in sources.items():
            if _sha256_file(path) != digest:
                raise ValueError("产品资料摘要不一致，已取消迁移")
            workbook = pd.read_excel(path, sheet_name=None, dtype=str)
            save_product_workbook(connection, digest, workbook)
            _verify_workbook(connection, path, workbook)
            count += 1
            rows += len(workbook["产品信息汇总表"])
    return {"workbooks": count, "rows": rows}


def _verify_workbook(
    connection: sqlite3.Connection, path: Path, workbook: dict[str, pd.DataFrame]
) -> None:
    restored = product_workbook(connection, path)
    if list(restored) != list(workbook):
        raise ValueError("产品资料工作表对账失败")
    for name, frame in workbook.items():
        pd.testing.assert_frame_equal(
            frame.fillna("").astype(str), restored[name], check_dtype=False
        )


def verify_product_artifacts(database: Database) -> int:
    """回退旧代码前只读核对导出产物，避免遗漏切换后的修改。"""
    with database.connect() as connection:
        connection.execute("PRAGMA query_only = ON")
        sources = product_sources(connection)
        for digest, path in sources.items():
            if _sha256_file(path) != digest:
                raise ValueError("产品导出产物摘要不一致，禁止直接回退旧代码")
            _verify_workbook(
                connection, path, pd.read_excel(path, sheet_name=None, dtype=str)
            )
    return len(sources)


def require_product_store(connection: sqlite3.Connection) -> None:
    for digest in product_sources(connection):
        if (
            connection.execute(
                "SELECT 1 FROM product_workbooks WHERE sha256 = ?", (digest,)
            ).fetchone()
            is None
        ):
            raise RuntimeError("产品资料尚未入库，请停服执行数据库升级")
