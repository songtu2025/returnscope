from __future__ import annotations

import logging
import threading
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from functools import partial
from typing import Any

from web_backend.agent_runner import AgentRunner
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_contracts import SEGMENT_USER_LIMIT as USER_SEGMENT_LIMIT
from web_backend.tasks.worker_recovery import TaskWorkerRecoveryMixin
from web_backend.worker_health import WorkerHealthMixin, WorkerHealthState

logger = logging.getLogger(__name__)


class TaskWorker(TaskWorkerRecoveryMixin, WorkerHealthMixin):
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
        self._health = WorkerHealthState()

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
            try:
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
                        partial(self._segment_finished, segment_id)
                    )
                self._finalize_pending_results()
            except Exception as exc:
                self._record_error("Listing 监督循环异常", exc)
            self._stop.wait(1.0)

    def _record_error(self, message: str, error: BaseException) -> None:
        self._health.record_error(error)
        logger.error(
            message,
            exc_info=(type(error), error, error.__traceback__),
        )

    def _segment_finished(
        self,
        segment_id: str,
        future: Future[Any],
    ) -> None:
        try:
            error = future.exception()
        except CancelledError:
            error = None
        if error is not None:
            self._record_error("Listing 片段执行出现未处理异常", error)
        self._release(segment_id)

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
            self._recover_running_segments(connection, interrupted, task_ids, now)
            self._apply_pending_task_requests(connection, flagged_tasks, task_ids, now)
            for task_id in task_ids:
                self._refresh_recovered_task(connection, task_id, now)

    def _recover_interrupted_tasks(self) -> None:
        self._recover_interrupted_segments()
