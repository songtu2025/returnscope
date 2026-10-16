"""停服回填并逐字段核对反馈查询投影，失败整批回滚。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from return_semantics.data import read_return_file
from web_backend.dataset_files import _sha256_file
from web_backend.datasets.return_store import save_return_frame

if TYPE_CHECKING:
    from web_backend.database import Database


def backfill_return_store(database: Database) -> dict[str, int]:
    versions = 0
    count = 0
    with database.transaction(immediate=True) as connection:
        for source in connection.execute(
            "SELECT v.id,v.file_path,v.sha256,v.row_count FROM dataset_versions v "
            "JOIN datasets d ON d.id=v.dataset_id WHERE d.kind='returns'"
        ).fetchall():
            path = Path(source["file_path"])
            if _sha256_file(path) != source["sha256"]:
                raise ValueError("反馈文件摘要不一致，已取消迁移")
            frame = read_return_file(path).fillna("").astype(str)
            if len(frame) != source["row_count"]:
                raise ValueError("反馈文件行数不一致，已取消迁移")
            save_return_frame(connection, source["id"], frame)
            stored = connection.execute(
                "SELECT values_json FROM return_rows WHERE version_id=? ORDER BY row_index",
                (source["id"],),
            ).fetchall()
            pd.testing.assert_frame_equal(
                frame,
                pd.DataFrame(
                    [json.loads(row[0]) for row in stored], columns=frame.columns
                ),
                check_dtype=False,
            )
            versions += 1
            count += len(frame)
    return {"versions": versions, "rows": count}


def require_return_store(connection: sqlite3.Connection) -> None:
    if connection.execute(
        "SELECT 1 FROM dataset_versions v JOIN datasets d ON d.id=v.dataset_id "
        "LEFT JOIN return_rowsets s ON s.version_id=v.id "
        "WHERE d.kind='returns' AND (s.version_id IS NULL OR s.row_count<>v.row_count) LIMIT 1"
    ).fetchone():
        raise RuntimeError("反馈查询明细尚未入库，请停服执行数据库升级")
