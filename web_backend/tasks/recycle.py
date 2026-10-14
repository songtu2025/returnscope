"""回收站查询和不可恢复清理，保留结果依赖的最小来源记录。"""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from shutil import copy2
from tempfile import TemporaryDirectory
from typing import Any

from web_backend.analysis_cleanup_files import _file_entry, remove_cleanup_files
from web_backend.common import insert_audit, json_value
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_contracts import TaskRevisionConflict


class TaskRecycleService:
    def __init__(self, database: Database, data_dir: Path) -> None:
        self.database = database
        self.data_dir = data_dir

    def listings(
        self, *, q: str = "", page: int = 1, page_size: int = 20
    ) -> dict[str, Any]:
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError("分页参数不合法")
        with self.database.connect() as connection:
            where = """s.deleted_at IS NOT NULL AND s.purged_at IS NULL
                       AND (?='' OR instr(lower(t.title || ' ' || s.scope_json), lower(?))>0)"""
            total = connection.execute(
                f"SELECT COUNT(*) FROM task_segments s JOIN tasks t ON t.id=s.task_id WHERE {where}",
                (q, q),
            ).fetchone()[0]
            rows = connection.execute(
                f"""SELECT s.id,s.task_id,s.segment_key,s.scope_json,s.status,s.deleted_at,
                           t.title AS task_title,t.revision AS task_revision,
                           COALESCE(u.display_name,'历史记录') AS removed_by
                    FROM task_segments s JOIN tasks t ON t.id=s.task_id
                    LEFT JOIN users u ON u.id=s.deleted_by WHERE {where}
                    ORDER BY s.deleted_at DESC,s.id LIMIT ? OFFSET ?""",
                (q, q, page_size, (page - 1) * page_size),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["scope"] = json_value(item.pop("scope_json"), {})
            items.append(item)
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def purge(self, task_id: str, segment_key: str, revision: int, actor: str) -> None:
        # 文件删除无法参与 SQLite 事务，失败时恢复已清理的文件。
        with (
            TemporaryDirectory(prefix="listing-purge-") as backup_directory,
            ExitStack() as rollback,
        ):
            with self.database.transaction(immediate=True) as connection:
                row = connection.execute(
                    """SELECT s.*,t.revision AS task_revision FROM task_segments s
                       JOIN tasks t ON t.id=s.task_id WHERE s.task_id=? AND s.segment_key=?""",
                    (task_id, segment_key),
                ).fetchone()
                if row is None or row["purged_at"]:
                    raise ValueError("Listing 不存在或已永久删除")
                if row["task_revision"] != revision:
                    raise TaskRevisionConflict("任务已更新，请刷新后重试")
                if (
                    not row["deleted_at"]
                    or row["status"] == "running"
                    or row["removal_requested_at"]
                ):
                    raise ValueError("只能永久删除回收站中已停止的 Listing")
                files = self._exclusive_files(connection, dict(row))
                for index, entry in enumerate(files):
                    original = self.data_dir / entry["path"]
                    if original.exists():
                        backup = Path(backup_directory) / str(index)
                        copy2(original, backup)
                        rollback.callback(copy2, backup, original)
                if remove_cleanup_files(self.data_dir, files):
                    raise ValueError("执行文件清理未完成，记录仍在回收站，请重试")
                now = utc_now()
                connection.execute(
                    """UPDATE task_segments SET purged_at=?, result_file_path=NULL,
                       result_json_path=NULL,classification_keys_json='[]',model_policy_json=NULL,
                       variants_json='[]',error=NULL,requested_action=NULL,revision=revision+1
                       WHERE id=?""",
                    (now, row["id"]),
                )
                connection.execute(
                    "UPDATE tasks SET revision=revision+1 WHERE id=?", (task_id,)
                )
                insert_audit(
                    connection,
                    "task_segment",
                    row["id"],
                    "purge",
                    actor,
                    {
                        "task_id": task_id,
                        "segment_key": segment_key,
                        "deleted_at": row["deleted_at"],
                    },
                    {"purged_at": now, "deliverables_retained": True},
                )
            rollback.pop_all()

    def _exclusive_files(
        self, connection: Any, segment: dict[str, Any]
    ) -> list[dict[str, Any]]:
        root = self.data_dir.resolve()
        folder = root / "results" / segment["task_id"] / "segments"
        paths = {
            Path(value)
            for value in (segment["result_file_path"], segment["result_json_path"])
            if value
        }
        paths.update(folder.glob(f"{segment['id']}-analysis-v*.xlsx"))
        paths.add(folder / f"{segment['id']}-classifications.json")
        paths.update(
            path.with_suffix(f"{path.suffix}.tmp")
            for path in tuple(paths)
            if path.suffix == ".json"
        )
        files = []
        for path in paths:
            entry = _file_entry(path, root, set())
            # 只清理本执行项目录内的文件，不碰共享输入、缓存和其他任务产物。
            if path.resolve().parent != folder.resolve() or not path.name.startswith(
                f"{segment['id']}-"
            ):
                raise ValueError("执行文件不属于当前 Listing，拒绝清理")
            shared = connection.execute(
                """SELECT 1 FROM task_segments WHERE id!=? AND (result_file_path=? OR result_json_path=?)
                   UNION ALL SELECT 1 FROM tasks WHERE result_file_path=? OR results_json_path=?
                   UNION ALL SELECT 1 FROM dataset_versions WHERE file_path=? LIMIT 1""",
                (segment["id"], str(path), str(path), str(path), str(path), str(path)),
            ).fetchone()
            if not shared:
                files.append(entry)
        return files
