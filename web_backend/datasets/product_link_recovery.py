"""停服升级时只恢复有完整留痕、且能与当前工作簿核对的商品关联。"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pandas as pd

from web_backend.common import json_text, json_value
from web_backend.dashboards.product_scope import (
    PRODUCT_FILTERS,
    PRODUCT_SCOPE,
    capture_dashboard_product_scopes,
)
from web_backend.database import Database
from web_backend.dataset_files import PRODUCT_WORKSHEET
from web_backend.datasets.current_products import (
    product_identities,
    refresh_product_dependents,
)
from web_backend.datasets.product_aliases import save_product_aliases
from web_backend.datasets.product_store import save_product_workbook
from web_backend.security import utc_now


def _recorded_changes(
    connection: sqlite3.Connection, dataset_id: str, frame: pd.DataFrame
) -> tuple[
    list[tuple[list[tuple[str, str]], list[tuple[str, str]]]],
    list[tuple[str, pd.DataFrame]],
    str,
]:
    changes = []
    snapshots = []
    boundary = ""
    history = connection.execute(
        "SELECT action, before_json, after_json, created_at FROM audit_logs "
        "WHERE entity_type = 'dataset' AND entity_id = ? ORDER BY created_at DESC, rowid DESC",
        (dataset_id,),
    ).fetchall()
    working = frame.copy()
    for entry in history:
        if entry["action"] != "dimension_row_update":
            # 上传、追加商品或缺少完整原值的品类操作会中断可证明的行对应关系。
            boundary = entry["created_at"]
            break
        before, after = (
            json_value(entry["before_json"], {}),
            json_value(entry["after_json"], {}),
        )
        index = before.get("row_index")
        if (
            index not in working.index
            or not before.get("values")
            or before["values"].keys() != after.get("values", {}).keys()
        ):
            raise ValueError("商品修改留痕不足")
        if any(
            column not in working or str(working.at[index, column]) != str(value)
            for column, value in after.get("values", {}).items()
        ):
            raise ValueError("商品修改留痕与当前资料不一致")
        current = product_identities(working)
        for column, value in before["values"].items():
            working.at[index, column] = value
        changes.append((product_identities(working), current))
        snapshots.append((entry["created_at"], working.copy()))
    return list(reversed(changes)), snapshots, boundary


def _scope_origin_time(
    connection: sqlite3.Connection, dashboard_id: str, original: dict[str, list[str]]
) -> str:
    versions = connection.execute(
        "SELECT filters_json, created_at FROM dashboard_dataset_versions WHERE dashboard_id = ? "
        "ORDER BY version_no DESC",
        (dashboard_id,),
    ).fetchall()
    scope_time = versions[0]["created_at"]
    for version in versions:
        previous = json_value(version["filters_json"], {})
        if any(previous.get(key) != original.get(key) for key in PRODUCT_FILTERS):
            break
        scope_time = version["created_at"]
    return scope_time


def _source_product_identities(
    connection: sqlite3.Connection, dataset_id: str, dashboard_id: str
) -> set[tuple[str, str]]:
    allowed = {
        (item["store_site"], item["matched_msku"])
        for item in connection.execute(
            "SELECT DISTINCT r.store_site, r.matched_msku FROM classification_result_records r "
            "JOIN dashboard_dataset_sources s ON s.result_version_id = r.result_version_id "
            "JOIN dashboard_versions v ON v.dataset_version_id = s.dataset_version_id "
            "JOIN analysis_dashboards d ON d.current_version_id = v.id "
            "JOIN classification_result_versions result ON result.id = r.result_version_id "
            "JOIN classification_results c ON c.id = result.result_id "
            "JOIN dataset_versions p ON p.id = c.product_version_id "
            "WHERE d.id = ? AND p.dataset_id = ?",
            (dashboard_id, dataset_id),
        )
    }
    aliases = connection.execute(
        "SELECT * FROM product_identity_aliases WHERE dataset_id = ?", (dataset_id,)
    ).fetchall()
    allowed.update(
        (item["current_store"], item["current_msku"])
        for item in aliases
        if (item["store_site"], item["msku"]) in allowed
    )
    return allowed


def _legacy_scopes(
    connection: sqlite3.Connection,
    dataset_id: str,
    frame: pd.DataFrame,
    snapshots: list[tuple[str, pd.DataFrame]],
    boundary: str,
) -> tuple[dict[str, dict[str, list[str]]], int]:
    scopes = capture_dashboard_product_scopes(connection, dataset_id)
    unresolved = 0
    for dashboard_id, filters in scopes.items():
        row = connection.execute(
            "SELECT data.created_at, data.filters_json FROM dashboard_dataset_versions data "
            "JOIN dashboard_versions v ON v.dataset_version_id = data.id "
            "JOIN analysis_dashboards d ON d.current_version_id = v.id WHERE d.id = ?",
            (dashboard_id,),
        ).fetchone()
        original = json_value(row["filters_json"], {})
        if PRODUCT_SCOPE in original or not PRODUCT_FILTERS.intersection(original):
            continue
        scope_time = _scope_origin_time(connection, dashboard_id, original)
        if boundary and scope_time < boundary:
            # 不跨过整文件替换或无法完整还原的品类编辑去猜测旧商品范围。
            scopes[dashboard_id] = original
            unresolved += 1
            continue
        selected = frame
        for changed_at, previous in snapshots:
            if changed_at > scope_time:
                selected = previous
        allowed = _source_product_identities(connection, dataset_id, dashboard_id)
        tokens = [
            value
            for value in filters[PRODUCT_SCOPE]
            if json_value(value)[0] != dataset_id
        ]
        for product in selected.to_dict(orient="records"):
            identity = (str(product["店铺/站点"]).strip(), str(product["MSKU"]).strip())
            if identity in allowed and all(
                str(product.get(column, "")).strip() in original[name]
                for name, column in (
                    ("product_name", "产品名称"),
                    ("product_sku", "SKU"),
                )
                if name in original
            ):
                tokens.append(json_text([dataset_id, *identity]))
        scopes[dashboard_id] = {**original, PRODUCT_SCOPE: sorted(set(tokens))}
    return scopes, unresolved


def recover_product_links(
    database: Database, connection: sqlite3.Connection
) -> dict[str, int]:
    counts = {"recovered": 0, "unresolved": 0}
    datasets = connection.execute(
        """SELECT d.id, v.file_path, v.sha256 FROM datasets d JOIN dataset_versions v
        ON v.dataset_id = d.id AND v.version = d.current_version
        WHERE d.kind = 'products' AND d.archived_at IS NULL"""
    ).fetchall()
    for dataset in datasets:
        path = Path(dataset["file_path"])
        if not path.is_file():
            counts["unresolved"] += 1
            continue
        workbook = pd.read_excel(path, sheet_name=None, dtype=str)
        frame = workbook[PRODUCT_WORKSHEET].fillna("")
        save_product_workbook(connection, dataset["sha256"], workbook)
        connection.execute("SAVEPOINT recover_product_links")
        try:
            changes, snapshots, boundary = _recorded_changes(
                connection, dataset["id"], frame
            )
            for previous, current in changes:
                save_product_aliases(connection, dataset["id"], previous, current)
        except ValueError:
            connection.execute("ROLLBACK TO recover_product_links")
            counts["unresolved"] += 1
        else:
            scopes, unresolved = _legacy_scopes(
                connection, dataset["id"], frame, snapshots, boundary
            )
            counts["unresolved"] += unresolved
            refresh_product_dependents(
                database, connection, dataset["id"], utc_now(), product_scopes=scopes
            )
            counts["recovered"] += 1
        finally:
            connection.execute("RELEASE recover_product_links")
    logging.getLogger(__name__).info("商品关联恢复统计：%s", counts)
    return counts
