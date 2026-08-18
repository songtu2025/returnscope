from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from return_semantics.data import (
    PRODUCT_CATEGORY_COLUMNS,
    PRODUCT_COLUMNS,
    PRODUCT_DETAIL_COLUMNS,
    RETURN_COLUMNS,
    RETURN_STORE_COLUMN,
    read_return_csv,
)
from web_backend.common import add_audit, json_text, json_value, list_audit, new_id
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.settings import Settings

ALLOWED_EXTENSIONS = {
    "returns": {".csv"},
    "products": {".xlsx"},
}
PRODUCT_WORKSHEET = "产品信息汇总表"


class DatasetRevisionConflict(ValueError):
    pass


def _identifier_prefix(value: object) -> str:
    match = re.match(r"^([A-Za-z]+\d+)(?:-|$)", str(value or "").strip())
    return match.group(1).casefold() if match else ""


def _product_identity_conflicts(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [*PRODUCT_COLUMNS, *PRODUCT_DETAIL_COLUMNS]
    values = frame.reindex(columns=columns, fill_value="").fillna("")
    listing_prefixes = values["Listing"].map(_identifier_prefix)
    compared_columns = ["MSKU", "产品名称", "SKU"]
    conflict = pd.Series(False, index=values.index)
    for column in compared_columns:
        prefixes = values[column].map(_identifier_prefix)
        conflict |= (
            listing_prefixes.ne("") & prefixes.ne("") & prefixes.ne(listing_prefixes)
        )
    return values.loc[conflict]


def _inspect_returns(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = read_return_csv(path)
    missing = [column for column in RETURN_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"退货数据缺少字段：{', '.join(missing)}")
    valid_comments = int(frame["customer-comments"].fillna("").str.strip().ne("").sum())
    stores = (
        frame[RETURN_STORE_COLUMN].fillna("").astype(str).str.strip()
        if RETURN_STORE_COLUMN in frame.columns
        else pd.Series("", index=frame.index, dtype=str)
    )
    skus = frame["sku"].fillna("").astype(str).str.strip()
    comments = frame["customer-comments"].fillna("").astype(str)
    encoding_anomaly = comments.str.contains(
        r"(?:[A-Za-z][\u4e00-\u9fff]|[\u4e00-\u9fff][A-Za-z])",
        regex=True,
    )
    encoding_anomaly_rows = int(encoding_anomaly.sum())
    matching_key_ready = stores.ne("") & skus.ne("")
    matching_key_ready_rows = int(matching_key_ready.sum())
    quality = {
        "required_columns": len(RETURN_COLUMNS),
        "missing_required_columns": [],
        "valid_comment_rows": valid_comments,
        "valid_comment_rate": round(valid_comments / max(len(frame), 1) * 100, 2),
        "store_column_present": RETURN_STORE_COLUMN in frame.columns,
        "missing_store_rows": int(stores.eq("").sum()),
        "missing_sku_rows": int(skus.eq("").sum()),
        "matching_key_ready_rows": matching_key_ready_rows,
        "matching_key_ready_rate": round(
            matching_key_ready_rows / max(len(frame), 1) * 100,
            2,
        ),
        "stores": sorted(value for value in stores.unique().tolist() if value),
        "text_encoding_anomaly_rows": encoding_anomaly_rows,
        "text_encoding_anomaly_rate": round(
            encoding_anomaly_rows / max(len(frame), 1) * 100,
            2,
        ),
        "text_encoding_anomaly_examples": comments.loc[encoding_anomaly]
        .head(5)
        .tolist(),
    }
    return frame, quality


def _fill_missing_return_store(path: Path, default_store: str) -> None:
    clean_store = default_store.strip()
    if not clean_store:
        return
    frame = read_return_csv(path)
    if RETURN_STORE_COLUMN not in frame.columns:
        frame[RETURN_STORE_COLUMN] = clean_store
    else:
        stores = frame[RETURN_STORE_COLUMN].fillna("").astype(str).str.strip()
        frame.loc[stores.eq(""), RETURN_STORE_COLUMN] = clean_store
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def _inspect_products(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    try:
        frame = pd.read_excel(path, sheet_name=PRODUCT_WORKSHEET, dtype=str)
    except ValueError as exc:
        raise ValueError("商品维度缺少“产品信息汇总表”工作表") from exc
    missing = [column for column in PRODUCT_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"商品维度缺少字段：{', '.join(missing)}")
    complete = int(
        frame[PRODUCT_COLUMNS]
        .fillna("")
        .apply(lambda column: column.str.strip().ne(""))
        .all(axis=1)
        .sum()
    )
    missing_category_columns = [
        column for column in PRODUCT_CATEGORY_COLUMNS if column not in frame.columns
    ]
    if missing_category_columns:
        category_ready = pd.Series(False, index=frame.index)
    else:
        category_ready = (
            frame[PRODUCT_CATEGORY_COLUMNS]
            .fillna("")
            .apply(lambda column: column.str.strip().ne(""))
            .all(axis=1)
        )
    category_ready_rows = int(category_ready.sum())
    identity_conflicts = _product_identity_conflicts(frame)
    identity_conflict_rows = len(identity_conflicts)
    quality = {
        "required_columns": len(PRODUCT_COLUMNS),
        "missing_required_columns": [],
        "complete_rows": complete,
        "complete_rate": round(complete / max(len(frame), 1) * 100, 2),
        "missing_category_columns": missing_category_columns,
        "category_ready_rows": category_ready_rows,
        "category_ready_rate": round(
            category_ready_rows / max(len(frame), 1) * 100,
            2,
        ),
        "missing_category_rows": len(frame) - category_ready_rows,
        "product_identity_conflict_rows": identity_conflict_rows,
        "product_identity_conflict_rate": round(
            identity_conflict_rows / max(len(frame), 1) * 100,
            2,
        ),
        "product_identity_conflict_examples": [
            {
                "listing": str(row["Listing"]),
                "product_name": str(row["产品名称"]),
                "product_sku": str(row["SKU"]),
            }
            for row in identity_conflicts.head(5).to_dict(orient="records")
        ],
    }
    return frame, quality


def inspect_file(
    path: Path,
    kind: str,
) -> tuple[int, int, list[dict[str, str]], dict[str, Any]]:
    if path.suffix.lower() not in ALLOWED_EXTENSIONS.get(kind, set()):
        allowed = "、".join(sorted(ALLOWED_EXTENSIONS.get(kind, set())))
        raise ValueError(f"{kind} 仅支持 {allowed} 文件")
    if kind == "returns":
        frame, quality = _inspect_returns(path)
    elif kind == "products":
        frame, quality = _inspect_products(path)
    else:
        raise ValueError("未知数据类型")
    schema = [
        {"name": str(column), "type": str(frame[column].dtype)}
        for column in frame.columns
    ]
    return len(frame), len(frame.columns), schema, quality


class DatasetService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings

    def list(self, kind: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT d.*, u.display_name AS creator_name,
                   v.id AS version_id, v.original_name, v.row_count,
                   v.column_count, v.size_bytes, v.schema_json,
                   v.quality_json, v.created_at AS version_created_at
            FROM datasets d
            JOIN users u ON u.id = d.created_by
            LEFT JOIN dataset_versions v
              ON v.dataset_id = d.id AND v.version = d.current_version
            WHERE d.archived_at IS NULL
        """
        params: tuple[object, ...] = ()
        if kind:
            query += " AND d.kind = ?"
            params = (kind,)
        query += " ORDER BY d.updated_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._serialize(dict(row)) for row in rows]

    def get(self, dataset_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT d.*, u.display_name AS creator_name,
                       v.id AS version_id, v.original_name, v.row_count,
                       v.column_count, v.size_bytes, v.schema_json,
                       v.quality_json, v.created_at AS version_created_at
                FROM datasets d
                JOIN users u ON u.id = d.created_by
                LEFT JOIN dataset_versions v
                  ON v.dataset_id = d.id AND v.version = d.current_version
                WHERE d.id = ? AND d.archived_at IS NULL
                """,
                (dataset_id,),
            ).fetchone()
            if row is None:
                return None
            versions = connection.execute(
                """
                SELECT v.*, u.display_name AS creator_name
                FROM dataset_versions v
                JOIN users u ON u.id = v.created_by
                WHERE v.dataset_id = ?
                ORDER BY v.version DESC
                """,
                (dataset_id,),
            ).fetchall()
        item = self._serialize(dict(row))
        item["versions"] = [self._serialize_version(dict(value)) for value in versions]
        item["audit"] = list_audit(self.database, "dataset", dataset_id)
        return item

    def list_versions(self, kind: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT v.*, d.name AS dataset_name, d.kind, d.current_version,
                   u.display_name AS creator_name
            FROM dataset_versions v
            JOIN datasets d ON d.id = v.dataset_id
            JOIN users u ON u.id = v.created_by
            WHERE d.archived_at IS NULL
        """
        params: tuple[object, ...] = ()
        if kind:
            query += " AND d.kind = ?"
            params = (kind,)
        query += " ORDER BY v.created_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        output = []
        for row in rows:
            item = self._serialize_version(dict(row))
            item["version_id"] = item["id"]
            output.append(item)
        return output

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

    def version_file(
        self,
        dataset_id: str,
        version: int | None = None,
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT v.file_path, v.original_name, v.content_type, v.version
                FROM dataset_versions v
                JOIN datasets d ON d.id = v.dataset_id
                WHERE v.dataset_id = ? AND d.archived_at IS NULL
                  AND v.version = COALESCE(?, d.current_version)
                """,
                (dataset_id, version),
            ).fetchone()
        return dict(row) if row else None

    def product_scopes(self, version_id: str) -> list[dict[str, Any]]:
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

    def create(
        self,
        name: str,
        kind: str,
        description: str,
        source_path: Path,
        original_name: str,
        content_type: str,
        change_note: str,
        actor_id: str,
        default_store: str = "",
    ) -> dict[str, Any]:
        dataset_id = new_id("ds")
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO datasets(
                    id, name, kind, description, current_version,
                    created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    dataset_id,
                    name.strip(),
                    kind,
                    description.strip(),
                    actor_id,
                    now,
                    now,
                ),
            )
        try:
            self.add_version(
                dataset_id=dataset_id,
                source_path=source_path,
                original_name=original_name,
                content_type=content_type,
                change_note=change_note or "创建首个版本",
                actor_id=actor_id,
                default_store=default_store,
            )
        except Exception:
            with self.database.transaction() as connection:
                connection.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
            raise
        add_audit(
            self.database,
            "dataset",
            dataset_id,
            "create",
            actor_id,
            after={"name": name, "kind": kind},
        )
        return self.get(dataset_id) or {}

    def add_version(
        self,
        dataset_id: str,
        source_path: Path,
        original_name: str,
        content_type: str,
        change_note: str,
        actor_id: str,
        expected_current_version: int | None = None,
        default_store: str = "",
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            dataset = connection.execute(
                "SELECT * FROM datasets WHERE id = ? AND archived_at IS NULL",
                (dataset_id,),
            ).fetchone()
        if dataset is None:
            raise ValueError("数据集不存在")
        kind = str(dataset["kind"])
        if kind == "returns":
            _fill_missing_return_store(source_path, default_store)
        row_count, column_count, schema, quality = inspect_file(source_path, kind)
        digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        version_id = new_id("dsv")

        with self.database.transaction(immediate=True) as connection:
            current = connection.execute(
                "SELECT current_version FROM datasets WHERE id = ?",
                (dataset_id,),
            ).fetchone()
            if (
                expected_current_version is not None
                and int(current["current_version"]) != expected_current_version
            ):
                raise DatasetRevisionConflict("商品维度已被其他用户修改，请刷新后重试")
            version = int(current["current_version"]) + 1
            destination = (
                self.settings.data_dir
                / "uploads"
                / dataset_id
                / f"v{version}{source_path.suffix.lower()}"
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination)
            now = utc_now()
            connection.execute(
                """
                INSERT INTO dataset_versions(
                    id, dataset_id, version, file_path, original_name,
                    content_type, size_bytes, sha256, row_count, column_count,
                    schema_json, quality_json, change_note, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    dataset_id,
                    version,
                    str(destination),
                    original_name,
                    content_type,
                    destination.stat().st_size,
                    digest,
                    row_count,
                    column_count,
                    json_text(schema),
                    json_text(quality),
                    change_note.strip(),
                    actor_id,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE datasets
                SET current_version = ?, updated_at = ?
                WHERE id = ?
                """,
                (version, now, dataset_id),
            )
        add_audit(
            self.database,
            "dataset",
            dataset_id,
            "add_version",
            actor_id,
            after={
                "version": version,
                "version_id": version_id,
                "default_store": default_store.strip(),
            },
        )
        return self.get(dataset_id) or {}

    def preview_rows(
        self,
        dataset_id: str,
        offset: int = 0,
        limit: int = 50,
        query: str = "",
        store: str = "",
        category: str = "",
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT d.kind, d.current_version, v.file_path
                FROM datasets d
                JOIN dataset_versions v
                  ON v.dataset_id = d.id AND v.version = d.current_version
                WHERE d.id = ? AND d.archived_at IS NULL
                """,
                (dataset_id,),
            ).fetchone()
        if row is None:
            raise ValueError("数据集不存在")
        if row["kind"] == "products":
            frame = pd.read_excel(
                Path(str(row["file_path"])),
                sheet_name=PRODUCT_WORKSHEET,
                dtype=str,
            ).fillna("")
        else:
            frame = read_return_csv(Path(str(row["file_path"]))).fillna("")
        source_total = len(frame)
        stores = (
            sorted(
                value
                for value in frame["店铺/站点"]
                .astype(str)
                .str.strip()
                .unique()
                .tolist()
                if value
            )
            if "店铺/站点" in frame.columns
            else []
        )
        if {"品类A", "品类B"}.issubset(frame.columns):
            category_labels = (
                frame[["品类A", "品类B"]]
                .astype(str)
                .apply(
                    lambda values: " > ".join(
                        value.strip() for value in values if value.strip()
                    ),
                    axis=1,
                )
            )
            categories = sorted(
                value for value in category_labels.unique().tolist() if value
            )
        else:
            category_labels = pd.Series("", index=frame.index, dtype=str)
            categories = []
        clean_store = store.strip()
        if clean_store and "店铺/站点" in frame.columns:
            frame = frame.loc[
                frame["店铺/站点"].astype(str).str.strip().eq(clean_store)
            ]
            category_labels = category_labels.loc[frame.index]
        clean_category = category.strip()
        if clean_category:
            frame = frame.loc[category_labels.eq(clean_category)]
        clean_query = query.strip().lower()
        if clean_query:
            searchable = frame.astype(str).apply(
                lambda column: column.str.lower().str.contains(
                    clean_query,
                    regex=False,
                )
            )
            frame = frame.loc[searchable.any(axis=1)]
        selected = frame.iloc[offset : offset + limit].copy()
        records = selected.astype(str).to_dict(orient="records")
        for row_index, record in zip(selected.index, records, strict=True):
            record["_row_index"] = int(row_index)
        return {
            "records": records,
            "offset": offset,
            "limit": limit,
            "total": len(frame),
            "source_total": source_total,
            "query": query,
            "version": int(row["current_version"]),
            "facets": {"stores": stores, "categories": categories},
        }

    def update_product_row(
        self,
        dataset_id: str,
        row_index: int,
        expected_version: int,
        changes: dict[str, str],
        change_note: str,
        actor_id: str,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT d.kind, d.current_version, v.file_path,
                       v.original_name, v.content_type
                FROM datasets d
                JOIN dataset_versions v
                  ON v.dataset_id = d.id AND v.version = d.current_version
                WHERE d.id = ? AND d.archived_at IS NULL
                """,
                (dataset_id,),
            ).fetchone()
        if row is None or row["kind"] != "products":
            raise ValueError("商品维度不存在")
        if int(row["current_version"]) != expected_version:
            raise DatasetRevisionConflict("商品维度已被其他用户修改，请刷新后重试")
        source_path = Path(str(row["file_path"]))
        workbook = pd.read_excel(
            source_path,
            sheet_name=None,
            dtype=str,
        )
        frame = workbook.get(PRODUCT_WORKSHEET)
        if frame is None:
            raise ValueError("商品维度缺少“产品信息汇总表”工作表")
        if row_index < 0 or row_index >= len(frame):
            raise ValueError("要修改的数据行不存在")
        allowed = {column for column in changes if column in frame.columns}
        if not allowed:
            raise ValueError("没有可修改的字段")
        before = {
            column: ""
            if pd.isna(frame.at[row_index, column])
            else str(frame.at[row_index, column])
            for column in allowed
        }
        normalized_changes = {
            column: str(changes[column]).strip() for column in allowed
        }
        changed = {
            column for column in allowed if before[column] != normalized_changes[column]
        }
        if not changed:
            raise ValueError("内容没有变化，无需创建新版本")
        for column in changed:
            frame.at[row_index, column] = normalized_changes[column]
        for column in PRODUCT_COLUMNS:
            value = frame.at[row_index, column]
            if pd.isna(value) or not str(value).strip():
                raise ValueError(f"{column} 不能为空")
        temp_path = self.settings.data_dir / "tmp" / f"{new_id('dimension')}.xlsx"
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with pd.ExcelWriter(temp_path, engine="openpyxl") as writer:
                for sheet_name, sheet in workbook.items():
                    sheet.to_excel(writer, sheet_name=sheet_name, index=False)
            result = self.add_version(
                dataset_id=dataset_id,
                source_path=temp_path,
                original_name=str(row["original_name"]),
                content_type=str(row["content_type"]),
                change_note=change_note or f"修改商品维度第 {row_index + 2} 行",
                actor_id=actor_id,
                expected_current_version=expected_version,
            )
        finally:
            temp_path.unlink(missing_ok=True)
        add_audit(
            self.database,
            "dataset",
            dataset_id,
            "dimension_row_update",
            actor_id,
            before={"row_index": row_index, "values": before},
            after={
                "row_index": row_index,
                "values": {column: normalized_changes[column] for column in changed},
                "note": change_note.strip(),
            },
        )
        return self.get(dataset_id) or result

    def complete_product_categories(
        self,
        dataset_id: str,
        expected_version: int,
        store: str | None,
        items: list[dict[str, str]],
        change_note: str,
        actor_id: str,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT d.kind, d.current_version, v.file_path,
                       v.original_name, v.content_type
                FROM datasets d
                JOIN dataset_versions v
                  ON v.dataset_id = d.id AND v.version = d.current_version
                WHERE d.id = ? AND d.archived_at IS NULL
                """,
                (dataset_id,),
            ).fetchone()
        if row is None or row["kind"] != "products":
            raise ValueError("商品维度不存在")
        if int(row["current_version"]) != expected_version:
            raise DatasetRevisionConflict("商品维度已被其他用户修改，请刷新后重试")
        fallback_store = (store or "").strip()

        normalized_items = []
        seen_products: set[tuple[str, str]] = set()
        for item in items:
            normalized = {
                key: str(item.get(key, "")).strip()
                for key in (
                    "store",
                    "msku",
                    "listing",
                    "category_a",
                    "category_b",
                    "product_name",
                )
            }
            normalized["store"] = normalized["store"] or fallback_store
            if not all(
                normalized[key]
                for key in ("store", "msku", "listing", "category_a", "category_b")
            ):
                raise ValueError("店铺、MSKU、Listing、品类A 和品类B 均不能为空")
            product_key = (normalized["store"], normalized["msku"])
            if product_key in seen_products:
                raise ValueError(
                    f"商品重复提交：{normalized['store']} + {normalized['msku']}"
                )
            seen_products.add(product_key)
            normalized_items.append(normalized)

        source_path = Path(str(row["file_path"]))
        workbook = pd.read_excel(source_path, sheet_name=None, dtype=str)
        frame = workbook.get(PRODUCT_WORKSHEET)
        if frame is None:
            raise ValueError("商品维度缺少“产品信息汇总表”工作表")
        for column in PRODUCT_CATEGORY_COLUMNS:
            if column not in frame.columns:
                frame[column] = ""
        before_items = []
        for item in normalized_items:
            msku_values = frame["MSKU"].fillna("").astype(str).str.strip()
            store_values = frame["店铺/站点"].fillna("").astype(str).str.strip()
            matching = frame.index[
                msku_values.eq(item["msku"]) & store_values.eq(item["store"])
            ].tolist()
            if matching:
                before_items.append(
                    {
                        "msku": item["msku"],
                        "store": item["store"],
                        "rows": [int(index) for index in matching],
                        "category_a": str(frame.at[matching[0], "品类A"] or ""),
                        "category_b": str(frame.at[matching[0], "品类B"] or ""),
                    }
                )
                for index in matching:
                    frame.at[index, "Listing"] = item["listing"]
                    frame.at[index, "品类A"] = item["category_a"]
                    frame.at[index, "品类B"] = item["category_b"]
                    if "产品名称" in frame.columns and item["product_name"]:
                        frame.at[index, "产品名称"] = item["product_name"]
                continue
            new_row = {column: "" for column in frame.columns}
            new_row.update(
                {
                    "MSKU": item["msku"],
                    "店铺/站点": item["store"],
                    "Listing": item["listing"],
                    "品类A": item["category_a"],
                    "品类B": item["category_b"],
                }
            )
            if "产品名称" in frame.columns:
                new_row["产品名称"] = item["product_name"]
            frame.loc[len(frame)] = new_row
            before_items.append(
                {"store": item["store"], "msku": item["msku"], "rows": []}
            )

        workbook[PRODUCT_WORKSHEET] = frame
        temp_path = self.settings.data_dir / "tmp" / f"{new_id('dimension')}.xlsx"
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with pd.ExcelWriter(temp_path, engine="openpyxl") as writer:
                for sheet_name, sheet in workbook.items():
                    sheet.to_excel(writer, sheet_name=sheet_name, index=False)
            result = self.add_version(
                dataset_id=dataset_id,
                source_path=temp_path,
                original_name=str(row["original_name"]),
                content_type=str(row["content_type"]),
                change_note=change_note,
                actor_id=actor_id,
                expected_current_version=expected_version,
            )
        finally:
            temp_path.unlink(missing_ok=True)
        add_audit(
            self.database,
            "dataset",
            dataset_id,
            "dimension_category_completion",
            actor_id,
            before={"items": before_items},
            after={
                "store": fallback_store,
                "items": normalized_items,
                "note": change_note.strip(),
            },
        )
        return self.get(dataset_id) or result

    @staticmethod
    def _serialize(item: dict[str, Any]) -> dict[str, Any]:
        item["schema"] = json_value(item.pop("schema_json", None), [])
        item["quality"] = json_value(item.pop("quality_json", None), {})
        return item

    @staticmethod
    def _serialize_version(item: dict[str, Any]) -> dict[str, Any]:
        item.pop("file_path", None)
        item["schema"] = json_value(item.pop("schema_json", None), [])
        item["quality"] = json_value(item.pop("quality_json", None), {})
        return item
