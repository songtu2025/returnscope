"""执行停止后完成移除；成功、失败和中断共用同一收尾。"""

import sqlite3

from web_backend.common import insert_audit, json_text
from web_backend.database import Database
from web_backend.security import utc_now


def finish_pending_removals(connection: sqlite3.Connection, task_id: str) -> None:
    rows = connection.execute(
        """SELECT id, segment_key, deleted_by FROM task_segments
           WHERE task_id=? AND removal_requested_at IS NOT NULL
             AND status!='running' AND deleted_at IS NULL""",
        (task_id,),
    ).fetchall()
    for row in rows:
        now = utc_now()
        connection.execute(
            """UPDATE task_segments SET deleted_at=?, removal_requested_at=NULL,
               requested_action=NULL, revision=revision+1 WHERE id=?""",
            (now, row["id"]),
        )
        connection.execute(
            """INSERT INTO task_events(task_id,event_type,stage,message,actor_id,data_json,created_at)
               VALUES(?,'segment_delete','移除完成','Listing 已移入回收站',?,?,?)""",
            (
                task_id,
                row["deleted_by"],
                json_text({"segment_key": row["segment_key"]}),
                now,
            ),
        )
        insert_audit(
            connection,
            "task_segment",
            row["id"],
            "remove",
            row["deleted_by"],
            after={"task_id": task_id, "deleted_at": now},
        )


def fail_pending_removal(database: Database, segment_id: str) -> bool:
    """检查点收尾失败时保留有效记录，允许用户检查存储后重新移除。"""
    with database.transaction(immediate=True) as connection:
        row = connection.execute(
            "SELECT task_id,deleted_by FROM task_segments WHERE id=? AND removal_requested_at IS NOT NULL AND deleted_at IS NULL",
            (segment_id,),
        ).fetchone()
        if row is None:
            return False
        connection.execute(
            "UPDATE tasks SET revision=revision+1 WHERE id=?", (row["task_id"],)
        )
        message = "移除未完成：执行数据保存失败，请检查存储后重试"
        connection.execute(
            """UPDATE task_segments SET status='failed',removal_requested_at=NULL,
               requested_action=NULL,error=?,revision=revision+1 WHERE id=?""",
            (message, segment_id),
        )
        insert_audit(
            connection,
            "task_segment",
            segment_id,
            "remove_failed",
            row["deleted_by"],
            after={"task_id": row["task_id"], "message": message},
        )
    return True
