from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path

import pandas as pd

from web_backend.common import new_id
from web_backend.database import Database
from web_backend.dataset_files import PRODUCT_WORKSHEET
from web_backend.settings import Settings

logger = logging.getLogger(__name__)
_preview_locks: dict[str, threading.Lock] = {}
_preview_locks_guard = threading.Lock()


class StorageFilesMixin:
    database: Database
    settings: Settings

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
            except OSError as error:
                logger.warning("商品预览清理失败: error_type=%s", type(error).__name__)

    def _safe_unlink_unreferenced(self, path_value: str) -> int:
        path = Path(path_value)
        uploads_root = (self.settings.data_dir / "uploads").resolve()
        try:
            resolved = path.resolve()
            if not resolved.is_relative_to(uploads_root):
                return 0
        except OSError as error:
            logger.warning("存储文件路径解析失败: error_type=%s", type(error).__name__)
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
