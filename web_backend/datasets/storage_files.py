from __future__ import annotations

import shutil
from pathlib import Path

from web_backend.common import new_id
from web_backend.database import Database
from web_backend.settings import Settings


class StorageFilesMixin:
    database: Database
    settings: Settings

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
