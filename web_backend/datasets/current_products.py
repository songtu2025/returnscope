"""维护一份当前商品资料，修订号仅用于并发校验。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from web_backend.common import insert_audit, json_text, json_value
from web_backend.dataset_files import PRODUCT_WORKSHEET, DatasetRevisionConflict


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
        raise ValueError("商品信息不存在")
    if write.expected_current_version != source["version"]:
        raise DatasetRevisionConflict("商品信息已被其他用户修改，请刷新后重试")
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
    if write.prepared.get("manual_edit"):
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


def sync_product_display(
    connection: Any,
    dataset_id: str,
    previous_identities: list[tuple[str, str]] | None = None,
) -> None:
    """只同步商品展示字段，不改写已计算的品类、Listing 或分类语义。"""
    source = connection.execute(
        """SELECT v.file_path FROM datasets d JOIN dataset_versions v
        ON v.dataset_id = d.id AND v.version = d.current_version WHERE d.id = ?""",
        (dataset_id,),
    ).fetchone()
    if source is None:
        return
    frame = pd.read_excel(
        Path(source["file_path"]), sheet_name=PRODUCT_WORKSHEET, dtype=str
    ).fillna("")
    grouped: dict[tuple[str, str], list[dict[Any, Any]]] = {}
    identities = product_identities(frame)
    for index, product in enumerate(frame.to_dict(orient="records")):
        identity = identities[index]
        grouped.setdefault(identity, []).append(product)
        if previous_identities and index < len(previous_identities):
            previous = previous_identities[index]
            if previous != identity:
                grouped.setdefault(previous, []).append(product)
    for identity, products in grouped.items():
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
) -> None:
    from web_backend.dashboards.live_sources import refresh_related_dashboards

    sync_product_display(connection, dataset_id, previous_identities)
    refresh_related_dashboards(
        database, connection, None, now, product_dataset_id=dataset_id
    )
