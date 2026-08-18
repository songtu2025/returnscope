from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from web_backend.agent_runner import AgentRunner
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_state import summarize_task_status

USER_SEGMENT_LIMIT = 3


class TaskWorker:
    def __init__(
        self,
        database: Database,
        runner: AgentRunner,
        concurrency: int,
    ) -> None:
        self.database = database
        self.runner = runner
        self.concurrency = concurrency
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._executor = ThreadPoolExecutor(max_workers=concurrency)
        self._active: set[str] = set()
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._recover_interrupted_segments()
        self._thread = threading.Thread(
            target=self._loop,
            name="listing-worker-supervisor",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._executor.shutdown(wait=False, cancel_futures=True)

    @property
    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                capacity = self.concurrency - len(self._active)
            for _ in range(max(capacity, 0)):
                claimed = self._claim_next_segment()
                if claimed is None:
                    break
                task_id, segment_id = claimed
                with self._lock:
                    self._active.add(segment_id)
                future = self._executor.submit(
                    self.runner.run_segment,
                    task_id,
                    segment_id,
                )
                future.add_done_callback(
                    lambda _future, claimed_id=segment_id: self._release(claimed_id)
                )
            self._finalize_pending_results()
            self._stop.wait(1.0)

    def _claim_next_segment(self) -> tuple[str, str] | None:
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                """
                SELECT s.id AS segment_id, s.task_id
                FROM task_segments s
                JOIN tasks t ON t.id = s.task_id
                WHERE s.status IN ('queued', 'retry_pending')
                  AND t.status IN ('queued', 'running')
                  AND t.cancel_requested = 0
                  AND t.pause_requested = 0
                  AND (
                      SELECT COUNT(*) FROM task_segments active
                      WHERE active.task_id = t.id AND active.status = 'running'
                  ) < t.max_parallel_segments
                  AND (
                      SELECT COUNT(*)
                      FROM task_segments owner_active
                      JOIN tasks owner_task ON owner_task.id = owner_active.task_id
                      WHERE owner_task.owner_id = t.owner_id
                        AND owner_active.status = 'running'
                  ) < ?
                ORDER BY
                  (
                      SELECT COUNT(*) FROM task_segments active
                      WHERE active.task_id = t.id AND active.status = 'running'
                  ) ASC,
                  COALESCE(t.last_scheduled_at, t.created_at) ASC,
                  s.execution_order ASC,
                  s.created_at ASC
                LIMIT 1
                """,
                (USER_SEGMENT_LIMIT,),
            ).fetchone()
            if row is None:
                return None
            now = utc_now()
            updated = connection.execute(
                """
                UPDATE task_segments
                SET status = 'running', requested_action = NULL,
                    error = NULL, started_at = COALESCE(started_at, ?),
                    completed_at = NULL, heartbeat_at = ?, revision = revision + 1
                WHERE id = ? AND status IN ('queued', 'retry_pending')
                """,
                (now, now, row["segment_id"]),
            )
            if updated.rowcount != 1:
                return None
            connection.execute(
                """
                UPDATE tasks
                SET status = 'running', stage = '语义分析',
                    message = 'Listing 片段正在运行',
                    started_at = COALESCE(started_at, ?), heartbeat_at = ?,
                    last_scheduled_at = ?, revision = revision + 1
                WHERE id = ?
                """,
                (now, now, now, row["task_id"]),
            )
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, data_json, created_at
                ) VALUES (?, 'segment_started', '语义分析',
                          'Listing 片段已获得运行槽位', ?, ?)
                """,
                (
                    row["task_id"],
                    f'{{"segment_id":"{row["segment_id"]}"}}',
                    now,
                ),
            )
            return str(row["task_id"]), str(row["segment_id"])

    def _release(self, segment_id: str) -> None:
        with self._lock:
            self._active.discard(segment_id)

    def _finalize_pending_results(self) -> None:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT t.id
                FROM tasks t
                JOIN task_segments s ON s.task_id = t.id
                WHERE t.status IN ('completed', 'partial', 'cancelled')
                  AND t.result_file_path IS NULL
                  AND t.error IS NULL
                  AND s.status IN ('completed', 'completed_with_errors')
                """
            ).fetchall()
        for row in rows:
            self.runner.finalize_task(str(row["id"]))

    def _recover_interrupted_segments(self) -> None:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            flagged_tasks = connection.execute(
                """
                SELECT id, cancel_requested, pause_requested
                FROM tasks
                WHERE (cancel_requested = 1 OR pause_requested = 1)
                  AND status NOT IN ('cancelled', 'completed', 'failed')
                """
            ).fetchall()
            interrupted = connection.execute(
                """
                SELECT s.id, s.task_id, s.requested_action,
                       t.cancel_requested, t.pause_requested
                FROM task_segments s
                JOIN tasks t ON t.id = s.task_id
                WHERE s.status = 'running'
                """
            ).fetchall()
            task_ids: set[str] = set()
            for segment in interrupted:
                requested_action = str(segment["requested_action"] or "")
                if requested_action == "cancel" or segment["cancel_requested"]:
                    status = "cancelled"
                    error = None
                elif requested_action == "pause" or segment["pause_requested"]:
                    status = "paused"
                    error = None
                else:
                    status = "retry_pending"
                    error = "服务重启，Listing 等待从检查点恢复"
                connection.execute(
                    """
                    UPDATE task_segments
                    SET status = ?, requested_action = NULL, error = ?,
                        started_at = CASE WHEN ? = 'retry_pending' THEN NULL
                                          ELSE started_at END,
                        completed_at = CASE WHEN ? = 'cancelled' THEN ? ELSE NULL END,
                        heartbeat_at = ?, revision = revision + 1
                    WHERE id = ?
                    """,
                    (status, error, status, status, now, now, segment["id"]),
                )
                task_ids.add(str(segment["task_id"]))

            for task in flagged_tasks:
                task_id = str(task["id"])
                if task["cancel_requested"]:
                    connection.execute(
                        """
                        UPDATE task_segments
                        SET status = 'cancelled', requested_action = NULL,
                            error = NULL, completed_at = ?, heartbeat_at = ?,
                            revision = revision + 1
                        WHERE task_id = ?
                          AND status IN (
                              'queued', 'retry_pending', 'paused',
                              'not_started', 'blocked', 'failed'
                          )
                        """,
                        (now, now, task_id),
                    )
                elif task["pause_requested"]:
                    connection.execute(
                        """
                        UPDATE task_segments
                        SET status = 'paused', requested_action = NULL,
                            heartbeat_at = ?, revision = revision + 1
                        WHERE task_id = ?
                          AND status IN ('queued', 'retry_pending', 'not_started')
                        """,
                        (now, task_id),
                    )
                task_ids.add(task_id)

            for task_id in task_ids:
                task = connection.execute(
                    """
                    SELECT cancel_requested, pause_requested
                    FROM tasks WHERE id = ?
                    """,
                    (task_id,),
                ).fetchone()
                statuses = [
                    str(row["status"])
                    for row in connection.execute(
                        "SELECT status FROM task_segments WHERE task_id = ?",
                        (task_id,),
                    ).fetchall()
                ]
                has_running = "running" in statuses
                if task and task["cancel_requested"] and not has_running:
                    task_status = "cancelled"
                elif task and task["pause_requested"] and not has_running:
                    task_status = "paused"
                else:
                    task_status = summarize_task_status(statuses)
                stage = {
                    "queued": "等待恢复",
                    "paused": "已暂停",
                    "cancelled": "已取消",
                    "partial": "部分完成",
                    "failed": "运行失败",
                    "blocked": "等待品类处理",
                    "completed": "分析完成",
                    "running": "语义分析",
                }[task_status]
                connection.execute(
                    """
                    UPDATE tasks
                    SET status = ?, stage = ?,
                        message = '服务重启后已恢复 Listing 状态',
                        completed_at = CASE
                            WHEN ? IN ('cancelled', 'completed', 'partial',
                                       'failed', 'blocked')
                            THEN COALESCE(completed_at, ?)
                            ELSE NULL
                        END,
                        heartbeat_at = ?, revision = revision + 1
                    WHERE id = ?
                    """,
                    (task_status, stage, task_status, now, now, task_id),
                )
                connection.execute(
                    """
                    INSERT INTO task_events(
                        task_id, event_type, stage, message, created_at
                    ) VALUES (?, 'recovered', ?,
                              '服务重启后 Listing 状态已恢复', ?)
                    """,
                    (task_id, stage, now),
                )

    def _recover_interrupted_tasks(self) -> None:
        self._recover_interrupted_segments()
