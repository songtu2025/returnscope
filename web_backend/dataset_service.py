from __future__ import annotations

import hashlib
import re
import shutil
import threading
from datetime import datetime, timedelta, timezone
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
_preview_locks: dict[str, threading.Lock] = {}
_preview_locks_guard = threading.Lock()


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
        r"(?:[A-Za-z][一-鿿]|[一-鿿][A-Za-z])",
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _inspect_file_with_frame(
    path: Path,
    kind: str,
) -> tuple[pd.DataFrame, int, int, list[dict[str, str]], dict[str, Any]]:
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
    return frame, len(frame), len(frame.columns), schema, quality


def inspect_file(
    path: Path,
    kind: str,
) -> tuple[int, int, list[dict[str, str]], dict[str, Any]]:
    _, row_count, column_count, schema, quality = _inspect_file_with_frame(path, kind)
    return row_count, column_count, schema, quality


def _return_source_key(stores: list[str]) -> str:
    normalized = sorted(
        {
            re.sub(r"\s+", "", str(value)).upper()
            for value in stores
            if str(value).strip()
        }
    )
    return "|".join(normalized)


def _return_source_name(stores: list[str], original_name: str) -> str:
    if stores:
        labels = [re.sub(r"[:_/\\-]+", " ", value).strip() for value in stores]
        return f"{'、'.join(labels)} 退货数据"
    stem = re.sub(r"[_-]+", " ", Path(original_name).stem).strip()
    return f"{stem or '未命名'} 退货数据"


class DatasetService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings

    def list(
        self,
        kind: str | None = None,
        usage_scope: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT d.*, u.display_name AS creator_name,
                   (SELECT COUNT(DISTINCT task.id)
                    FROM dataset_versions referenced_version
                    JOIN tasks task
                      ON task.dataset_version_id = referenced_version.id
                      OR task.product_version_id = referenced_version.id
                    WHERE referenced_version.dataset_id = d.id
                   ) AS task_reference_count,
                   v.id AS version_id, v.original_name, v.row_count,
                   v.column_count, v.size_bytes, v.schema_json,
                   v.quality_json, v.created_at AS version_created_at
            FROM datasets d
            JOIN users u ON u.id = d.created_by
            LEFT JOIN dataset_versions v
              ON v.dataset_id = d.id AND v.version = d.current_version
            WHERE d.archived_at IS NULL
        """
        params: list[object] = []
        if kind:
            query += " AND d.kind = ?"
            params.append(kind)
        if usage_scope:
            query += " AND d.usage_scope = ?"
            params.append(usage_scope)
        query += " ORDER BY d.updated_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._serialize(dict(row)) for row in rows]

    def get(
        self,
        dataset_id: str,
        include: set[str] | None = None,
    ) -> dict[str, Any] | None:
        requested = {"versions", "imports", "audit"} if include is None else include
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT d.*, u.display_name AS creator_name,
                       (SELECT COUNT(DISTINCT task.id)
                        FROM dataset_versions referenced_version
                        JOIN tasks task
                          ON task.dataset_version_id = referenced_version.id
                          OR task.product_version_id = referenced_version.id
                        WHERE referenced_version.dataset_id = d.id
                       ) AS task_reference_count,
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
            versions = (
                connection.execute(
                    """
                    SELECT v.*, u.display_name AS creator_name
                    FROM dataset_versions v
                    JOIN users u ON u.id = v.created_by
                    WHERE v.dataset_id = ?
                    ORDER BY v.version DESC
                    """,
                    (dataset_id,),
                ).fetchall()
                if "versions" in requested
                else []
            )
            imports = (
                connection.execute(
                    """
                    SELECT i.*, u.display_name AS creator_name
                    FROM dataset_imports i
                    JOIN users u ON u.id = i.created_by
                    WHERE i.dataset_id = ?
                    ORDER BY i.created_at DESC, i.id DESC
                    """,
                    (dataset_id,),
                ).fetchall()
                if "imports" in requested
                else []
            )
        item = self._serialize(dict(row))
        if "versions" in requested:
            item["versions"] = [
                self._serialize_version(dict(value)) for value in versions
            ]
        if "imports" in requested:
            item["imports"] = [self._serialize_import(dict(value)) for value in imports]
        if "audit" in requested:
            item["audit"] = list_audit(self.database, "dataset", dataset_id)
        return item

    def list_versions(self, kind: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT v.*, d.name AS dataset_name, d.kind, d.current_version,
                   d.source_key, d.usage_scope,
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

    @staticmethod
    def _normalize_dataset_ids(dataset_ids: list[str]) -> list[str]:
        values = list(
            dict.fromkeys(str(dataset_id).strip() for dataset_id in dataset_ids)
        )
        values = [value for value in values if value]
        if not values:
            raise ValueError("请选择需要管理的数据源")
        if len(values) > 100:
            raise ValueError("一次最多管理 100 个数据源")
        return values

    def _storage_rows(self, dataset_ids: list[str]) -> list[dict[str, Any]]:
        placeholders = ",".join("?" for _ in dataset_ids)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT v.id, v.dataset_id, v.version, v.file_path,
                       v.original_name, v.size_bytes, v.sha256, v.created_at,
                       d.current_version,
                       (SELECT COUNT(*) FROM tasks t
                        WHERE t.dataset_version_id = v.id
                           OR t.product_version_id = v.id) AS task_references,
                       (SELECT COUNT(*) FROM dataset_imports i
                        WHERE i.resulting_version_id = v.id) AS import_references
                FROM dataset_versions v
                JOIN datasets d ON d.id = v.dataset_id
                WHERE d.archived_at IS NULL
                  AND d.id IN ({placeholders})
                ORDER BY v.dataset_id, v.version DESC
                """,
                tuple(dataset_ids),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _expired_version_ids(
        rows: list[dict[str, Any]],
        retention_days: int,
        retain_latest: int,
    ) -> set[str]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        positions: dict[str, int] = {}
        candidates: set[str] = set()
        for row in rows:
            dataset_id = str(row["dataset_id"])
            position = positions.get(dataset_id, 0) + 1
            positions[dataset_id] = position
            if int(row["version"]) == int(row["current_version"]):
                continue
            if int(row["task_references"]) or int(row["import_references"]):
                continue
            if position <= retain_latest:
                continue
            created_at = datetime.fromisoformat(
                str(row["created_at"]).replace("Z", "+00:00")
            )
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if created_at < cutoff:
                candidates.add(str(row["id"]))
        return candidates

    @staticmethod
    def _path_size(path_value: str, fallback: int) -> int:
        path = Path(path_value)
        return path.stat().st_size if path.exists() else int(fallback)

    def _uploads_size(self) -> int:
        uploads_root = self.settings.data_dir / "uploads"
        if not uploads_root.exists():
            return 0
        return sum(
            path.stat().st_size for path in uploads_root.rglob("*") if path.is_file()
        )

    def storage_summary(
        self,
        dataset_ids: list[str],
        retention_days: int = 30,
        retain_latest: int = 2,
    ) -> dict[str, Any]:
        clean_ids = self._normalize_dataset_ids(dataset_ids)
        rows = self._storage_rows(clean_ids)
        if not rows:
            raise ValueError("没有可管理的快照")

        path_sizes: dict[str, int] = {}
        digest_paths: dict[str, set[str]] = {}
        for row in rows:
            path_value = str(row["file_path"])
            path_sizes.setdefault(
                path_value,
                self._path_size(path_value, int(row["size_bytes"])),
            )
            digest_paths.setdefault(str(row["sha256"]), set()).add(path_value)

        duplicate_groups = 0
        dedup_reclaimable_bytes = 0
        for paths in digest_paths.values():
            if len(paths) < 2:
                continue
            duplicate_groups += 1
            sizes = [path_sizes[path] for path in paths]
            dedup_reclaimable_bytes += sum(sizes) - max(sizes)

        expired_ids = self._expired_version_ids(
            rows,
            retention_days,
            retain_latest,
        )
        expired_paths: dict[str, int] = {}
        for row in rows:
            if str(row["id"]) in expired_ids:
                path_value = str(row["file_path"])
                expired_paths[path_value] = expired_paths.get(path_value, 0) + 1
        expired_reclaimable_bytes = 0
        if expired_paths:
            placeholders = ",".join("?" for _ in expired_paths)
            with self.database.connect() as connection:
                path_references = {
                    str(row["file_path"]): int(row["references_count"])
                    for row in connection.execute(
                        f"""
                        SELECT file_path, COUNT(*) AS references_count
                        FROM dataset_versions
                        WHERE file_path IN ({placeholders})
                        GROUP BY file_path
                        """,
                        tuple(expired_paths),
                    ).fetchall()
                }
            expired_reclaimable_bytes = sum(
                path_sizes[path]
                for path, candidate_count in expired_paths.items()
                if path_references.get(path, 0) == candidate_count
            )

        logical_bytes = sum(int(row["size_bytes"]) for row in rows)
        physical_bytes = sum(path_sizes.values())
        task_referenced_versions = sum(
            1 for row in rows if int(row["task_references"]) > 0
        )
        return {
            "dataset_ids": clean_ids,
            "version_count": len(rows),
            "logical_bytes": logical_bytes,
            "physical_bytes": physical_bytes,
            "current_versions": sum(
                1 for row in rows if int(row["version"]) == int(row["current_version"])
            ),
            "task_referenced_versions": task_referenced_versions,
            "task_reference_count": sum(int(row["task_references"]) for row in rows),
            "duplicate_groups": duplicate_groups,
            "dedup_reclaimable_bytes": dedup_reclaimable_bytes,
            "expired_versions": len(expired_ids),
            "expired_reclaimable_bytes": expired_reclaimable_bytes,
            "retention_days": retention_days,
            "retain_latest": retain_latest,
            "can_cleanup": bool(dedup_reclaimable_bytes or expired_ids),
        }

    def _blob_path(self, digest: str, suffix: str) -> Path:
        return self.settings.data_dir / "uploads" / "blobs" / f"{digest}{suffix}"

    def _ensure_blob(self, source_path: Path, digest: str) -> Path:
        destination = self._blob_path(digest, source_path.suffix.lower())
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(source_path, destination)
        return destination

    def _preview_path(self, digest: str) -> Path:
        return (
            self.settings.data_dir
            / "cache"
            / "dataset-previews"
            / f"{digest}.csv"
        )

    def _ensure_product_preview(
        self,
        source_path: Path,
        digest: str,
        frame: pd.DataFrame | None = None,
    ) -> Path:
        destination = self._preview_path(digest)
        if destination.exists():
            return destination
        with _preview_locks_guard:
            lock = _preview_locks.setdefault(digest, threading.Lock())
        with lock:
            if destination.exists():
                return destination
            preview_frame = frame
            if preview_frame is None:
                preview_frame = pd.read_excel(
                    source_path,
                    sheet_name=PRODUCT_WORKSHEET,
                    dtype=str,
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(
                f"{destination.name}.{new_id('tmp')}"
            )
            try:
                preview_frame.to_csv(temporary, index=False, encoding="utf-8-sig")
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        return destination

    def _remove_unreferenced_preview(self, digest: str) -> None:
        with self.database.connect() as connection:
            referenced = connection.execute(
                """
                SELECT 1
                FROM dataset_versions v
                JOIN datasets d ON d.id = v.dataset_id
                WHERE v.sha256 = ? AND d.kind = 'products'
                LIMIT 1
                """,
                (digest,),
            ).fetchone()
        if referenced is None:
            try:
                self._preview_path(digest).unlink(missing_ok=True)
            except OSError:
                pass

    def _safe_unlink_unreferenced(self, path_value: str) -> int:
        path = Path(path_value)
        uploads_root = (self.settings.data_dir / "uploads").resolve()
        try:
            resolved = path.resolve()
            if not resolved.is_relative_to(uploads_root):
                return 0
        except OSError:
            return 0
        with self.database.connect() as connection:
            referenced = connection.execute(
                "SELECT 1 FROM dataset_versions WHERE file_path = ? LIMIT 1",
                (path_value,),
            ).fetchone()
        if referenced is not None or not path.exists():
            return 0
        size = path.stat().st_size
        path.unlink()
        return size

    def _deduplicate_storage(self, rows: list[dict[str, Any]]) -> int:
        digests: dict[str, set[str]] = {}
        for row in rows:
            digests.setdefault(str(row["sha256"]), set()).add(str(row["file_path"]))
        duplicate_digests = [
            digest for digest, paths in digests.items() if len(paths) > 1
        ]
        removed_files = 0
        for digest in duplicate_digests:
            with self.database.connect() as connection:
                matching = connection.execute(
                    """
                    SELECT file_path FROM dataset_versions
                    WHERE sha256 = ? ORDER BY created_at, id
                    """,
                    (digest,),
                ).fetchall()
            source_paths = list(
                dict.fromkeys(str(row["file_path"]) for row in matching)
            )
            source = next(
                (Path(value) for value in source_paths if Path(value).exists()), None
            )
            if source is None:
                continue
            canonical = self._ensure_blob(source, digest)
            canonical_value = str(canonical)
            with self.database.transaction(immediate=True) as connection:
                connection.execute(
                    "UPDATE dataset_versions SET file_path = ? WHERE sha256 = ?",
                    (canonical_value, digest),
                )
            for path_value in source_paths:
                if path_value == canonical_value:
                    continue
                removed_bytes = self._safe_unlink_unreferenced(path_value)
                if removed_bytes:
                    removed_files += 1
        return removed_files

    def cleanup_storage(
        self,
        dataset_ids: list[str],
        retention_days: int,
        retain_latest: int,
        actor_id: str,
    ) -> dict[str, Any]:
        clean_ids = self._normalize_dataset_ids(dataset_ids)
        before = self.storage_summary(
            clean_ids,
            retention_days,
            retain_latest,
        )
        disk_bytes_before = self._uploads_size()
        rows = self._storage_rows(clean_ids)
        deduplicated_files = self._deduplicate_storage(rows)
        rows = self._storage_rows(clean_ids)
        expired_ids = self._expired_version_ids(
            rows,
            retention_days,
            retain_latest,
        )
        removed_paths: list[str] = []
        removed_digests: list[str] = []
        pruned_versions = 0
        if expired_ids:
            with self.database.transaction(immediate=True) as connection:
                for row in rows:
                    if str(row["id"]) not in expired_ids:
                        continue
                    deleted = connection.execute(
                        """
                        DELETE FROM dataset_versions
                        WHERE id = ?
                          AND version <> ?
                          AND NOT EXISTS (
                              SELECT 1 FROM tasks t
                              WHERE t.dataset_version_id = dataset_versions.id
                                 OR t.product_version_id = dataset_versions.id
                          )
                          AND NOT EXISTS (
                              SELECT 1 FROM dataset_imports i
                              WHERE i.resulting_version_id = dataset_versions.id
                          )
                        """,
                        (row["id"], row["current_version"]),
                    )
                    if deleted.rowcount:
                        pruned_versions += 1
                        removed_paths.append(str(row["file_path"]))
                        removed_digests.append(str(row["sha256"]))
            for path_value in set(removed_paths):
                self._safe_unlink_unreferenced(path_value)
            for digest in set(removed_digests):
                self._remove_unreferenced_preview(digest)

        after = self.storage_summary(
            clean_ids,
            retention_days,
            retain_latest,
        )
        disk_bytes_after = self._uploads_size()
        result = {
            "before": before,
            "after": after,
            "deduplicated_files": deduplicated_files,
            "pruned_versions": pruned_versions,
            "freed_bytes": max(disk_bytes_before - disk_bytes_after, 0),
        }
        for dataset_id in clean_ids:
            add_audit(
                self.database,
                "dataset",
                dataset_id,
                "cleanup_storage",
                actor_id,
                before=before,
                after=result,
            )
        return result

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

    def inspect_return_import(
        self,
        source_path: Path,
        original_name: str,
        actor_id: str | None = None,
        content_type: str = "text/csv",
    ) -> dict[str, Any]:
        row_count, column_count, schema, quality = inspect_file(
            source_path,
            "returns",
        )
        raw_sha256 = _sha256_file(source_path)
        stores = [str(value) for value in quality.get("stores", [])]
        source_key = _return_source_key(stores)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT d.id AS dataset_id, d.name AS dataset_name,
                       d.source_key, d.current_version,
                       v.id AS version_id, v.row_count, v.quality_json,
                       v.created_at AS version_created_at
                FROM datasets d
                JOIN dataset_versions v
                  ON v.dataset_id = d.id AND v.version = d.current_version
                WHERE d.kind = 'returns'
                  AND d.usage_scope = 'managed'
                  AND d.archived_at IS NULL
                ORDER BY d.updated_at DESC, d.id
                """
            ).fetchall()
            duplicate = connection.execute(
                """
                SELECT i.id AS import_id, i.dataset_id,
                       i.resulting_version_id AS version_id,
                       i.mode, i.created_at,
                       d.name AS dataset_name, d.usage_scope
                FROM dataset_imports i
                JOIN datasets d ON d.id = i.dataset_id
                WHERE i.raw_sha256 = ? AND d.archived_at IS NULL
                ORDER BY i.created_at DESC, i.id DESC
                LIMIT 1
                """,
                (raw_sha256,),
            ).fetchone()
            if duplicate is None:
                duplicate = connection.execute(
                    """
                    SELECT NULL AS import_id, v.dataset_id,
                           v.id AS version_id, 'legacy' AS mode,
                           v.created_at, d.name AS dataset_name,
                           d.usage_scope
                    FROM dataset_versions v
                    JOIN datasets d ON d.id = v.dataset_id
                    WHERE v.sha256 = ? AND d.archived_at IS NULL
                    ORDER BY v.created_at DESC, v.id DESC
                    LIMIT 1
                    """,
                    (raw_sha256,),
                ).fetchone()
        matches = []
        for row in rows:
            item = dict(row)
            item_quality = json_value(item.pop("quality_json", None), {})
            item_source_key = str(item.get("source_key") or "") or _return_source_key(
                item_quality.get("stores", [])
            )
            if source_key and item_source_key == source_key:
                item["source_key"] = item_source_key
                matches.append(item)
        inspection = {
            "original_name": original_name,
            "raw_sha256": raw_sha256,
            "row_count": row_count,
            "column_count": column_count,
            "schema": schema,
            "quality": quality,
            "stores": stores,
            "source_key": source_key,
            "suggested_name": _return_source_name(stores, original_name),
            "matches": matches,
            "duplicate": dict(duplicate) if duplicate is not None else None,
        }
        if actor_id is not None:
            self._cleanup_staged_imports()
            inspection_id = new_id("inspection")
            created_at = datetime.now(timezone.utc)
            expires_at = created_at + timedelta(minutes=30)
            with self.database.transaction(immediate=True) as connection:
                connection.execute(
                    """
                    INSERT INTO dataset_import_staging(
                        id, owner_id, temp_path, original_name, content_type,
                        size_bytes, sha256, inspection_json, created_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        inspection_id,
                        actor_id,
                        str(source_path),
                        original_name,
                        content_type,
                        source_path.stat().st_size,
                        raw_sha256,
                        json_text(inspection),
                        created_at.isoformat(),
                        expires_at.isoformat(),
                    ),
                )
            inspection["inspection_id"] = inspection_id
        return inspection

    def _cleanup_staged_imports(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.database.transaction(immediate=True) as connection:
            rows = connection.execute(
                """
                SELECT id, temp_path FROM dataset_import_staging
                WHERE expires_at <= ? AND consumed_at IS NULL
                """,
                (now,),
            ).fetchall()
            connection.execute(
                """
                DELETE FROM dataset_import_staging
                WHERE expires_at <= ? AND consumed_at IS NULL
                """,
                (now,),
            )
        for row in rows:
            Path(str(row["temp_path"])).unlink(missing_ok=True)

    def import_staged_returns(
        self,
        *,
        inspection_id: str,
        actor_id: str,
        mode: str,
        dataset_id: str = "",
        name: str = "",
        change_note: str = "",
    ) -> dict[str, Any]:
        self._cleanup_staged_imports()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT * FROM dataset_import_staging WHERE id = ?",
                (inspection_id,),
            ).fetchone()
            if row is None:
                raise ValueError("文件检查记录已过期，请重新选择文件")
            if str(row["owner_id"]) != actor_id:
                raise ValueError("无权使用该文件检查记录")
            if row["consumed_at"]:
                raise ValueError("该文件已完成导入，不能重复提交")
            if not Path(str(row["temp_path"])).exists():
                raise ValueError("待导入文件已不存在，请重新选择文件")
            connection.execute(
                "UPDATE dataset_import_staging SET consumed_at = ? WHERE id = ?",
                (utc_now(), inspection_id),
            )
        path = Path(str(row["temp_path"]))
        try:
            result = self.import_returns(
                source_path=path,
                original_name=str(row["original_name"]),
                content_type=str(row["content_type"]),
                mode=mode,
                actor_id=actor_id,
                dataset_id=dataset_id,
                name=name,
                change_note=change_note,
                _inspection=json_value(row["inspection_json"], {}),
            )
        except Exception:
            with self.database.transaction(immediate=True) as connection:
                connection.execute(
                    "UPDATE dataset_import_staging SET consumed_at = NULL WHERE id = ?",
                    (inspection_id,),
                )
            raise
        try:
            with self.database.transaction(immediate=True) as connection:
                connection.execute(
                    "DELETE FROM dataset_import_staging WHERE id = ?",
                    (inspection_id,),
                )
        except Exception:
            pass
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return result

    def import_returns(
        self,
        *,
        source_path: Path,
        original_name: str,
        content_type: str,
        mode: str,
        actor_id: str,
        dataset_id: str = "",
        name: str = "",
        change_note: str = "",
        _inspection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if mode not in {"analyze_only", "create", "append", "replace"}:
            raise ValueError("未知的退货数据导入方式")
        inspection = _inspection or self.inspect_return_import(source_path, original_name)
        duplicate = inspection.get("duplicate")
        duplicate_in_target = duplicate and (
            mode == "analyze_only"
            or (mode == "create" and duplicate.get("usage_scope") == "managed")
            or str(duplicate["dataset_id"]) == dataset_id
        )
        if duplicate_in_target:
            existing = self.get(str(duplicate["dataset_id"]))
            if existing is not None:
                return {
                    "dataset": existing,
                    "version_id": str(duplicate["version_id"]),
                    "duplicate": True,
                    "mode": mode,
                    "inspection": inspection,
                    "summary": {
                        "imported_row_count": 0,
                        "skipped_row_count": int(inspection["row_count"]),
                    },
                }

        target = None
        if mode in {"append", "replace"}:
            target = self.get(dataset_id)
            if target is None or target["kind"] != "returns":
                raise ValueError("请选择有效的退货数据源")
            if target.get("usage_scope") != "managed":
                raise ValueError("一次性任务数据不能作为长期数据源更新")
            target_source_key = str(target.get("source_key") or "")
            if (
                target_source_key
                and inspection["source_key"]
                and target_source_key != inspection["source_key"]
            ):
                raise ValueError("上传文件与所选数据源的店铺/站点不一致")

        import_id = new_id("dataset_import")
        raw_destination = (
            self.settings.data_dir
            / "imports"
            / import_id
            / f"source{source_path.suffix.lower()}"
        )
        raw_destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, raw_destination)
        imported_row_count = int(inspection["row_count"])
        skipped_row_count = 0
        generated_note = change_note.strip()
        try:
            if mode in {"analyze_only", "create"}:
                target = self.create(
                    name=name.strip() or str(inspection["suggested_name"]),
                    kind="returns",
                    description=(
                        "仅用于一次分析的退货明细"
                        if mode == "analyze_only"
                        else "持续维护的退货数据源"
                    ),
                    source_path=source_path,
                    original_name=original_name,
                    content_type=content_type,
                    change_note=generated_note or "首次导入退货数据",
                    actor_id=actor_id,
                    source_key=str(inspection["source_key"]),
                    usage_scope=("task_input" if mode == "analyze_only" else "managed"),
                    _inspection=inspection,
                )
            elif mode == "replace":
                assert target is not None
                target = self.add_version(
                    dataset_id=dataset_id,
                    source_path=source_path,
                    original_name=original_name,
                    content_type=content_type,
                    change_note=generated_note or "替换当前退货数据",
                    actor_id=actor_id,
                )
            else:
                assert target is not None
                current_version = next(
                    value
                    for value in target["versions"]
                    if value["version"] == target["current_version"]
                )
                with self.database.connect() as connection:
                    current_row = connection.execute(
                        "SELECT file_path FROM dataset_versions WHERE id = ?",
                        (current_version["id"],),
                    ).fetchone()
                current_frame = read_return_csv(Path(str(current_row["file_path"])))
                incoming_frame = read_return_csv(source_path)
                columns = list(
                    dict.fromkeys([*current_frame.columns, *incoming_frame.columns])
                )
                current_frame = current_frame.reindex(columns=columns)
                incoming_frame = incoming_frame.reindex(columns=columns)
                clean_current = current_frame.drop_duplicates(ignore_index=True)
                merged = pd.concat(
                    [clean_current, incoming_frame],
                    ignore_index=True,
                ).drop_duplicates(ignore_index=True)
                imported_row_count = max(len(merged) - len(clean_current), 0)
                skipped_row_count = max(len(incoming_frame) - imported_row_count, 0)
                merge_path = self.settings.data_dir / "tmp" / f"{new_id('merge')}.csv"
                merge_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    merged.to_csv(merge_path, index=False, encoding="utf-8-sig")
                    target = self.add_version(
                        dataset_id=dataset_id,
                        source_path=merge_path,
                        original_name=original_name,
                        content_type="text/csv",
                        change_note=generated_note or "追加一批退货数据",
                        actor_id=actor_id,
                    )
                finally:
                    merge_path.unlink(missing_ok=True)

            if target is None:
                raise ValueError("导入后未生成可用数据")
            version = next(
                value
                for value in target["versions"]
                if value["version"] == target["current_version"]
            )
            now = utc_now()
            with self.database.transaction(immediate=True) as connection:
                connection.execute(
                    """
                    UPDATE datasets
                    SET source_key = COALESCE(source_key, ?), updated_at = ?
                    WHERE id = ?
                    """,
                    (inspection["source_key"] or None, now, target["id"]),
                )
                connection.execute(
                    """
                    INSERT INTO dataset_imports(
                        id, dataset_id, resulting_version_id, mode,
                        raw_file_path, original_name, content_type, size_bytes,
                        raw_sha256, row_count, column_count, schema_json,
                        quality_json, source_key, imported_row_count,
                        skipped_row_count, created_by, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        import_id,
                        target["id"],
                        version["id"],
                        mode,
                        str(raw_destination),
                        original_name,
                        content_type,
                        raw_destination.stat().st_size,
                        inspection["raw_sha256"],
                        inspection["row_count"],
                        inspection["column_count"],
                        json_text(inspection["schema"]),
                        json_text(inspection["quality"]),
                        inspection["source_key"] or None,
                        imported_row_count,
                        skipped_row_count,
                        actor_id,
                        now,
                    ),
                )
            add_audit(
                self.database,
                "dataset",
                str(target["id"]),
                "import_returns",
                actor_id,
                after={
                    "import_id": import_id,
                    "mode": mode,
                    "version_id": version["id"],
                    "raw_sha256": inspection["raw_sha256"],
                    "imported_row_count": imported_row_count,
                    "skipped_row_count": skipped_row_count,
                },
            )
            refreshed = self.get(str(target["id"])) or target
            return {
                "dataset": refreshed,
                "version_id": version["id"],
                "duplicate": False,
                "mode": mode,
                "inspection": inspection,
                "summary": {
                    "imported_row_count": imported_row_count,
                    "skipped_row_count": skipped_row_count,
                },
            }
        except Exception:
            raw_destination.unlink(missing_ok=True)
            raw_destination.parent.rmdir()
            raise

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
        source_key: str = "",
        usage_scope: str = "managed",
        _inspection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        dataset_id = new_id("ds")
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO datasets(
                    id, name, kind, description, source_key, usage_scope,
                    current_version,
                    created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    dataset_id,
                    name.strip(),
                    kind,
                    description.strip(),
                    source_key.strip() or None,
                    usage_scope,
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
                _inspection=_inspection,
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
        _inspection: dict[str, Any] | None = None,
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
        inspected_frame: pd.DataFrame | None = None
        # 仅复用同次导入在服务端产生的检查结果，修改文件后必须重新检查。
        if _inspection is not None and not default_store:
            row_count = _inspection["row_count"]
            column_count = _inspection["column_count"]
            schema = _inspection["schema"]
            quality = _inspection["quality"]
            digest = _inspection["raw_sha256"]
        else:
            (
                inspected_frame,
                row_count,
                column_count,
                schema,
                quality,
            ) = _inspect_file_with_frame(source_path, kind)
            digest = _sha256_file(source_path)
        version_id = new_id("dsv")
        destination = self._ensure_blob(source_path, digest)
        if kind == "products":
            self._ensure_product_preview(destination, digest, inspected_frame)

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
        version: int | None = None,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT d.kind, d.current_version, v.version AS selected_version,
                       v.file_path, v.sha256, v.row_count, v.quality_json
                FROM datasets d
                JOIN dataset_versions v
                  ON v.dataset_id = d.id
                 AND v.version = COALESCE(?, d.current_version)
                WHERE d.id = ? AND d.archived_at IS NULL
                """,
                (version, dataset_id),
            ).fetchone()
        if row is None:
            raise ValueError("数据集或数据版本不存在")
        if row["kind"] == "products":
            preview_path = self._ensure_product_preview(
                Path(str(row["file_path"])),
                str(row["sha256"]),
            )
            frame = pd.read_csv(preview_path, dtype=str).fillna("")
        else:
            if not query.strip() and not store.strip() and not category.strip():
                frame = read_return_csv(
                    Path(str(row["file_path"])),
                    nrows=offset + limit,
                ).fillna("")
                selected = frame.iloc[offset : offset + limit].copy()
                records = selected.astype(str).to_dict(orient="records")
                for row_index, record in zip(selected.index, records, strict=True):
                    record["_row_index"] = int(row_index)
                quality = json_value(row["quality_json"], {}) or {}
                return {
                    "records": records,
                    "offset": offset,
                    "limit": limit,
                    "total": int(row["row_count"]),
                    "source_total": int(row["row_count"]),
                    "query": query,
                    "version": int(row["selected_version"]),
                    "facets": {
                        "stores": quality.get("stores", []),
                        "categories": [],
                    },
                }
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
            category_a = frame["品类A"].astype(str).str.strip()
            category_b = frame["品类B"].astype(str).str.strip()
            category_labels = category_a.where(
                category_b.eq(""),
                category_a + " > " + category_b,
            )
            category_labels = category_labels.where(category_a.ne(""), category_b)
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
            "version": int(row["selected_version"]),
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
        if item.get("kind") == "returns":
            stores = item["quality"].get("stores", [])
            if not item.get("source_key"):
                item["source_key"] = _return_source_key(stores)
            item["source_name"] = (
                _return_source_name(stores, "")
                if stores
                else str(item.get("name") or "未命名退货数据")
            )
        return item

    @staticmethod
    def _serialize_version(item: dict[str, Any]) -> dict[str, Any]:
        item.pop("file_path", None)
        item["schema"] = json_value(item.pop("schema_json", None), [])
        item["quality"] = json_value(item.pop("quality_json", None), {})
        if item.get("kind") == "returns":
            stores = item["quality"].get("stores", [])
            if not item.get("source_key"):
                item["source_key"] = _return_source_key(stores)
            item["source_name"] = (
                _return_source_name(stores, "")
                if stores
                else str(item.get("dataset_name") or "未命名退货数据")
            )
        return item

    @staticmethod
    def _serialize_import(item: dict[str, Any]) -> dict[str, Any]:
        item.pop("raw_file_path", None)
        item["schema"] = json_value(item.pop("schema_json", None), [])
        item["quality"] = json_value(item.pop("quality_json", None), {})
        return item
