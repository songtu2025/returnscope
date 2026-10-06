from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from web_backend.database import Database


class StorageReclamationMixin:
    database: Database
    _path_size: Callable[[str, int], int]
    _ensure_blob: Callable[[Path, str], Path]
    _safe_unlink_unreferenced: Callable[[str], int]
    _remove_unreferenced_preview: Callable[[str], None]

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

    def _storage_file_inventory(
        self, rows: list[dict[str, Any]]
    ) -> tuple[dict[str, int], dict[str, set[str]]]:
        path_sizes: dict[str, int] = {}
        digest_paths: dict[str, set[str]] = {}
        for row in rows:
            path_value = str(row["file_path"])
            path_sizes.setdefault(
                path_value,
                self._path_size(path_value, int(row["size_bytes"])),
            )
            digest_paths.setdefault(str(row["sha256"]), set()).add(path_value)
        return path_sizes, digest_paths

    @staticmethod
    def _deduplication_capacity(
        digest_paths: dict[str, set[str]], path_sizes: dict[str, int]
    ) -> tuple[int, int]:
        duplicate_groups = 0
        dedup_reclaimable_bytes = 0
        for paths in digest_paths.values():
            if len(paths) < 2:
                continue
            duplicate_groups += 1
            sizes = [path_sizes[path] for path in paths]
            dedup_reclaimable_bytes += sum(sizes) - max(sizes)
        return duplicate_groups, dedup_reclaimable_bytes

    def _expired_storage_capacity(
        self,
        rows: list[dict[str, Any]],
        expired_ids: set[str],
        path_sizes: dict[str, int],
    ) -> int:
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
        return expired_reclaimable_bytes

    def _deduplicate_digest(self, digest: str) -> int:
        removed_files = 0
        with self.database.connect() as connection:
            matching = connection.execute(
                """
                    SELECT file_path FROM dataset_versions
                    WHERE sha256 = ? ORDER BY created_at, id
                    """,
                (digest,),
            ).fetchall()
        source_paths = list(dict.fromkeys(str(row["file_path"]) for row in matching))
        source = next(
            (Path(value) for value in source_paths if Path(value).exists()), None
        )
        if source is None:
            return 0
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

    def _prune_storage_versions(
        self, rows: list[dict[str, Any]], expired_ids: set[str]
    ) -> int:
        removed_paths: list[str] = []
        removed_digests: list[str] = []
        pruned_versions = 0
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
        return pruned_versions
