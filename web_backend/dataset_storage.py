from __future__ import annotations

from typing import Any

from web_backend.common import add_audit
from web_backend.database import Database
from web_backend.datasets.storage_files import StorageFilesMixin
from web_backend.datasets.storage_files import shutil as shutil
from web_backend.datasets.storage_reclamation import StorageReclamationMixin
from web_backend.settings import Settings


class DatasetStorageMixin(StorageReclamationMixin, StorageFilesMixin):
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

        path_sizes, digest_paths = self._storage_file_inventory(rows)

        duplicate_groups, dedup_reclaimable_bytes = self._deduplication_capacity(
            digest_paths, path_sizes
        )

        expired_ids = self._expired_version_ids(
            rows,
            retention_days,
            retain_latest,
        )
        expired_reclaimable_bytes = self._expired_storage_capacity(
            rows, expired_ids, path_sizes
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

    def _deduplicate_storage(self, rows: list[dict[str, Any]]) -> int:
        digests: dict[str, set[str]] = {}
        for row in rows:
            digests.setdefault(str(row["sha256"]), set()).add(str(row["file_path"]))
        duplicate_digests = [
            digest for digest, paths in digests.items() if len(paths) > 1
        ]
        removed_files = 0
        for digest in duplicate_digests:
            removed_files += self._deduplicate_digest(digest)
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
        pruned_versions = 0
        if expired_ids:
            pruned_versions = self._prune_storage_versions(rows, expired_ids)

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
