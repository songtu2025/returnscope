"""维护一份当前产品资料，修订号仅用于并发校验。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from web_backend.common import insert_audit, json_text, json_value
from web_backend.dashboards.product_scope import capture_dashboard_product_scopes
from web_backend.database import Database
from web_backend.dataset_files import PRODUCT_WORKSHEET, DatasetRevisionConflict
from web_backend.datasets.product_aliases import product_aliases, save_product_aliases


def product_identities(frame: pd.DataFrame) -> list[tuple[str, str]]:
    values = frame[["店铺/站点", "MSKU"]].fillna("").astype(str)
    return [
        (store.strip(), msku.strip())
        for store, msku in values.itertuples(index=False, name=None)
    ]


def freeze_existing_product_inputs(connection: Any, source: Any) -> None:
    """旧任务缺少输入摘要时，在覆盖当前资料之前补齐。"""
    rows = connection.execute(
        "SELECT id, snapshot_json FROM tasks WHERE product_version_id = ?",
        (source["id"],),
    ).fetchall()
    for row in rows:
        snapshot = json_value(row["snapshot_json"], {})
        products = snapshot.setdefault("products", {})
        if products.get("sha256"):
            continue
        products.update(
            dataset_id=source["dataset_id"],
            version_id=source["id"],
            version=source["version"],
            sha256=source["sha256"],
        )
        connection.execute(
            "UPDATE tasks SET snapshot_json = ? WHERE id = ?",
            (json_text(snapshot), row["id"]),
        )


def update_current_products(connection: Any, write: Any, now: str) -> tuple[int, str]:
    source = connection.execute(
        """SELECT v.* FROM dataset_versions v JOIN datasets d ON d.id = v.dataset_id
        WHERE d.id = ? AND v.version = d.current_version""",
        (write.dataset_id,),
    ).fetchone()
    if source is None:
        raise ValueError("产品信息不存在")
    if write.expected_current_version != source["version"]:
        raise DatasetRevisionConflict("产品信息已被其他用户修改，请刷新后重试")
    freeze_existing_product_inputs(connection, source)
    revision = int(source["version"]) + 1
    fields = (
        "file_path",
        "original_name",
        "content_type",
        "size_bytes",
        "sha256",
        "row_count",
        "column_count",
        "schema_json",
        "quality_json",
        "change_note",
    )
    connection.execute(
        f"UPDATE dataset_versions SET {', '.join(f'{field} = ?' for field in fields)}, "
        "version = ?, created_by = ?, created_at = ? WHERE id = ?",
        (
            *[write.prepared[field] for field in fields],
            revision,
            write.actor_id,
            now,
            source["id"],
        ),
    )
    connection.execute(
        "UPDATE datasets SET current_version = ?, updated_at = ? WHERE id = ?",
        (revision, now, write.dataset_id),
    )
    if audit := write.prepared.get("product_audit"):
        insert_audit(
            connection,
            "dataset",
            write.dataset_id,
            audit["action"],
            write.actor_id,
            before=audit["before"],
            after=audit["after"],
            created_at=now,
        )
        return revision, str(source["id"])
    insert_audit(
        connection,
        "dataset",
        write.dataset_id,
        "product_update",
        write.actor_id,
        before={"sha256": source["sha256"], "row_count": source["row_count"]},
        after={
            "sha256": write.prepared["sha256"],
            "row_count": write.prepared["row_count"],
            "note": write.prepared["change_note"],
        },
        created_at=now,
    )
    return revision, str(source["id"])


@dataclass(frozen=True)
class ProductDisplaySnapshot:
    dataset_id: str
    file_path: str
    sha256: str
    frame: pd.DataFrame

    def current_frame(self, dataset_id: str, source: Any) -> pd.DataFrame:
        if (
            self.dataset_id != dataset_id
            or self.file_path != source["file_path"]
            or self.sha256 != source["sha256"]
        ):
            raise DatasetRevisionConflict("产品信息已更新，请重新生成分类结果")
        return self.frame


def load_product_display(
    database: Database, task_id: str
) -> ProductDisplaySnapshot | None:
    """在结果发布取得写锁前读取产品文件，提交时再核对当前文件摘要。"""
    with database.connect() as connection:
        source = connection.execute(
            """SELECT d.id AS dataset_id, v.file_path, v.sha256 FROM tasks t
            JOIN dataset_versions input ON input.id = t.product_version_id
            JOIN datasets d ON d.id = input.dataset_id
            JOIN dataset_versions v ON v.dataset_id = d.id AND v.version = d.current_version
            WHERE t.id = ?""",
            (task_id,),
        ).fetchone()
    if source is None:
        return None
    frame = _product_display_frame(source["dataset_id"], source)
    return ProductDisplaySnapshot(**dict(source), frame=frame)


def _product_display_frame(
    dataset_id: str, source: Any, snapshot: ProductDisplaySnapshot | None = None
) -> pd.DataFrame:
    if snapshot is not None:
        return snapshot.current_frame(dataset_id, source)
    return pd.read_excel(
        Path(source["file_path"]), sheet_name=PRODUCT_WORKSHEET, dtype=str
    ).fillna("")


def sync_product_display(
    connection: Any,
    dataset_id: str,
    previous_identities: list[tuple[str, str]] | None = None,
    *,
    snapshot: ProductDisplaySnapshot | None = None,
) -> None:
    """只同步商品展示字段，不改写已计算的品类、Listing 或分类语义。"""
    source = connection.execute(
        """SELECT v.file_path, v.sha256 FROM datasets d JOIN dataset_versions v
        ON v.dataset_id = d.id AND v.version = d.current_version WHERE d.id = ?""",
        (dataset_id,),
    ).fetchone()
    if source is None:
        return
    frame = _product_display_frame(dataset_id, source, snapshot)
    grouped: dict[tuple[str, str], list[dict[Any, Any]]] = {}
    identities = product_identities(frame)
    if previous_identities is not None:
        save_product_aliases(connection, dataset_id, previous_identities, identities)
    for index, product in enumerate(frame.to_dict(orient="records")):
        identity = identities[index]
        grouped.setdefault(identity, []).append(product)
    for previous, current in product_aliases(connection, dataset_id).items():
        if previous in grouped:
            raise ValueError("历史商品标识被重复使用，请核对店铺和 MSKU")
        if current in grouped:
            grouped[previous] = grouped[current]
    # 只处理已有结果引用的商品，避免持有写锁时遍历整个商品库发送无效更新。
    referenced = connection.execute(
        """SELECT DISTINCT record.store_site, record.matched_msku
        FROM classification_result_records record
        JOIN classification_result_versions version ON version.id = record.result_version_id
        JOIN classification_results result ON result.id = version.result_id
        JOIN dataset_versions product ON product.id = result.product_version_id
        WHERE product.dataset_id = ?""",
        (dataset_id,),
    ).fetchall()
    for reference in referenced:
        identity = tuple(reference)
        products = grouped.get(identity)
        if not products:
            continue
        product = products[0]
        fields = {
            name: str(product[column]).strip()
            for name, column in (
                ("product_name", "产品名称"),
                ("product_sku", "SKU"),
                ("asin", "ASIN"),
            )
            if column in product
            and len({str(item[column]).strip() for item in products}) == 1
        }
        if not fields:
            continue
        connection.execute(
            f"UPDATE classification_result_records SET {', '.join(f'{name} = ?' for name in fields)} "
            "WHERE store_site = ? AND matched_msku = ? AND result_version_id IN ("
            "SELECT v.id FROM classification_result_versions v JOIN classification_results r ON r.id = v.result_id "
            "JOIN dataset_versions p ON p.id = r.product_version_id WHERE p.dataset_id = ?)",
            (*fields.values(), *identity, dataset_id),
        )


def refresh_product_dependents(
    database: Any,
    connection: Any,
    dataset_id: str,
    now: str,
    *,
    previous_identities: list[tuple[str, str]] | None = None,
    product_scopes: dict[str, dict[str, list[str]]] | None = None,
) -> None:
    from web_backend.dashboards.live_sources import refresh_related_dashboards

    scopes = (
        product_scopes
        if product_scopes is not None
        else capture_dashboard_product_scopes(connection, dataset_id)
    )
    sync_product_display(connection, dataset_id, previous_identities)
    refresh_related_dashboards(
        database,
        connection,
        None,
        now,
        product_dataset_id=dataset_id,
        product_scopes=scopes,
    )
