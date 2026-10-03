from __future__ import annotations

import builtins
from pathlib import Path
from typing import Any

import pandas as pd

from return_semantics.data import PRODUCT_COLUMNS
from web_backend.common import json_value
from web_backend.database import Database
from web_backend.dataset_files import (
    PRODUCT_WORKSHEET,
)


class _DatasetReferences:
    database: Database

    def references(
        self,
        version_id: str,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            version = connection.execute(
                """
                SELECT v.id, v.dataset_id, v.version, v.sha256,
                       d.name AS dataset_name, d.kind
                FROM dataset_versions v
                JOIN datasets d ON d.id = v.dataset_id
                WHERE v.id = ?
                """,
                (version_id,),
            ).fetchone()
            if version is None:
                raise ValueError("数据版本不存在")
            total = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM tasks t
                    WHERE t.dataset_version_id = ? OR t.product_version_id = ?
                    """,
                    (version_id, version_id),
                ).fetchone()[0]
            )
            rows = connection.execute(
                """
                SELECT t.id AS task_id, t.title, t.status,
                       t.owner_id, owner.display_name AS owner_name,
                       t.created_at, t.snapshot_json,
                       CASE WHEN t.dataset_version_id = ?
                            THEN 'returns' ELSE 'products' END AS reference_type
                FROM tasks t
                LEFT JOIN users owner ON owner.id = t.owner_id
                WHERE t.dataset_version_id = ? OR t.product_version_id = ?
                ORDER BY t.created_at DESC, t.id ASC, reference_type ASC
                LIMIT ? OFFSET ?
                """,
                (
                    version_id,
                    version_id,
                    version_id,
                    page_size,
                    (page - 1) * page_size,
                ),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            snapshot = json_value(item.pop("snapshot_json"), {}) or {}
            item["owner"] = {
                "id": item.pop("owner_id"),
                "name": item.pop("owner_name"),
            }
            item["version_snapshot"] = snapshot.get(item["reference_type"], {})
            items.append(item)
        return {
            "version": {
                "id": version["id"],
                "dataset_id": version["dataset_id"],
                "name": version["dataset_name"],
                "kind": version["kind"],
                "version": int(version["version"]),
                "sha256": version["sha256"],
            },
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def product_scopes(self, version_id: str) -> builtins.list[dict[str, Any]]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT v.file_path, d.kind
                FROM dataset_versions v
                JOIN datasets d ON d.id = v.dataset_id
                WHERE v.id = ? AND d.archived_at IS NULL
                """,
                (version_id,),
            ).fetchone()
        if row is None or row["kind"] != "products":
            raise ValueError("商品维度版本不存在")
        frame = pd.read_excel(
            Path(str(row["file_path"])),
            sheet_name=PRODUCT_WORKSHEET,
            dtype=str,
            usecols=PRODUCT_COLUMNS,
        ).fillna("")
        frame["店铺/站点"] = frame["店铺/站点"].str.strip()
        frame["Listing"] = frame["Listing"].str.strip()
        output = []
        for store, rows in frame.loc[frame["店铺/站点"].ne("")].groupby(
            "店铺/站点",
            sort=True,
        ):
            output.append(
                {
                    "store": str(store),
                    "listings": sorted(
                        value for value in rows["Listing"].unique().tolist() if value
                    ),
                }
            )
        return output
