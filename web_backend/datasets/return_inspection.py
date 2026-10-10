from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from web_backend.common import json_text, new_id
from web_backend.database import Database
from web_backend.dataset_files import (
    _inspect_file_with_frame,
    _sha256_file,
)

STAGING_TTL_MINUTES = 30


def persist_return_inspection(
    database: Database,
    source_path: Path,
    actor_id: str,
    content_type: str,
    inspection: dict[str, Any],
) -> str:
    inspection_id = new_id("inspection")
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(minutes=STAGING_TTL_MINUTES)
    with database.transaction(immediate=True) as connection:
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
                inspection["original_name"],
                content_type,
                source_path.stat().st_size,
                inspection["raw_sha256"],
                json_text(inspection),
                created_at.isoformat(),
                expires_at.isoformat(),
            ),
        )
    return inspection_id


class DatasetFilePreparationMixin:
    _ensure_blob: Callable[..., Path]
    _ensure_product_preview: Callable[..., Path]
    _prepared_version: Callable[..., dict[str, Any]]

    def _prepare_dataset_file(
        self,
        source_path: Path,
        kind: str,
        inspection: dict[str, Any] | None,
        metadata: dict[str, str],
    ) -> dict[str, Any]:
        inspected_frame: pd.DataFrame | None = None
        # 仅复用同次导入在服务端产生的检查结果，修改文件后必须重新检查。
        if inspection is not None:
            row_count = inspection["row_count"]
            column_count = inspection["column_count"]
            schema = inspection["schema"]
            quality = inspection["quality"]
            digest = inspection["raw_sha256"]
        else:
            (
                inspected_frame,
                row_count,
                column_count,
                schema,
                quality,
            ) = _inspect_file_with_frame(source_path, kind)
            digest = _sha256_file(source_path)
        destination = self._ensure_blob(source_path, digest)
        if kind == "products":
            self._ensure_product_preview(destination, digest, inspected_frame)
        return self._prepared_version(
            destination,
            {**metadata, "change_note": metadata["change_note"].strip()},
            {
                "raw_sha256": digest,
                "row_count": row_count,
                "column_count": column_count,
                "schema": schema,
                "quality": quality,
            },
        )
