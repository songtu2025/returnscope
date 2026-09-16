from __future__ import annotations

import shutil
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from web_backend.common import add_audit, new_id
from web_backend.database import Database
from web_backend.dataset_files import PRODUCT_WORKSHEET
from web_backend.settings import Settings

_preview_locks: dict[str, threading.Lock] = {}
_preview_locks_guard = threading.Lock()


class DatasetStorageMixin:
    database: Database
    settings: Settings

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
        if destination.exists():
            return destination
        temporary = destination.with_name(f"{destination.name}.{new_id('blob')}")
        try:
            shutil.copy2(source_path, temporary)
            try:
                temporary.replace(destination)
            except OSError:
                if not destination.exists():
                    raise
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    def _preview_path(self, digest: str) -> Path:
        return self.settings.data_dir / "cache" / "dataset-previews" / f"{digest}.csv"

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
            temporary = destination.with_name(f"{destination.name}.{new_id('tmp')}")
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
