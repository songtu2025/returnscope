"""分类标准重新启用时复用已发布内容，不创建新版本。"""

import json
from collections.abc import Callable
from typing import Any

from web_backend.classification_standard_contracts import (
    ClassificationStandardConflict,
    ClassificationStandardNotFound,
)
from web_backend.common import add_audit
from web_backend.database import Database
from web_backend.security import utc_now


class StandardLifecycleMixin:
    database: Database
    _registry_compatibility_blocking: Callable[..., list[str]]
    get: Callable[[str], dict[str, Any]]

    def enable_standard(
        self, standard_id: str, expected_version_id: str, actor_id: str
    ) -> dict[str, Any]:
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                """
                SELECT s.status, s.current_version_id, v.snapshot_json,
                       v.status AS version_status
                FROM classification_standards s
                JOIN classification_standard_versions v
                  ON v.id = s.current_version_id
                WHERE s.id = ?
                """,
                (standard_id,),
            ).fetchone()
            if row is None:
                raise ClassificationStandardNotFound("分类标准不存在")
            if row["current_version_id"] != expected_version_id:
                raise ClassificationStandardConflict("标准已更新，请刷新后重新启用")
            if row["version_status"] != "published":
                raise ClassificationStandardConflict("请先检查草稿并保存启用")
            if row["status"] == "active":
                return self.get(standard_id)
            blocking = self._registry_compatibility_blocking(
                standard_id, json.loads(row["snapshot_json"])
            )
            if blocking:
                raise ClassificationStandardConflict("；".join(blocking))
            connection.execute(
                "UPDATE classification_standards SET status='active', updated_at=? "
                "WHERE id=?",
                (utc_now(), standard_id),
            )
        add_audit(
            self.database,
            "classification_standard",
            standard_id,
            "activate",
            actor_id,
            before={"status": "inactive"},
            after={"status": "active"},
        )
        return self.get(standard_id)
