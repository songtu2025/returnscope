from dataclasses import dataclass
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from web_backend.classification_standard_validation_worker import (
    ClassificationStandardValidationWorker,
)
from web_backend.database import Database
from web_backend.insight_report_worker import InsightReportWorker
from web_backend.security import utc_now
from web_backend.settings import Settings
from web_backend.task_service import TaskService
from web_backend.worker import TaskWorker


def _worker_health(worker: Any, enabled: bool) -> dict[str, Any]:
    health = (
        worker.health if enabled else {"last_error_type": None, "last_error_at": None}
    )
    if not enabled:
        status = "ok"
    elif not worker.is_alive:
        status = "unavailable"
    elif health["last_error_type"]:
        status = "degraded"
    else:
        status = "ok"
    return {
        "status": status,
        "last_error": health["last_error_type"],
        "last_error_at": health["last_error_at"],
    }


@dataclass(frozen=True)
class _MonitoringDependencies:
    task_service: TaskService
    worker: TaskWorker
    insight_report_worker: InsightReportWorker
    standard_validation_worker: ClassificationStandardValidationWorker
    start_worker: bool


def _register_health_route(
    router: APIRouter,
    database: Database,
    monitoring: _MonitoringDependencies,
) -> None:
    worker = monitoring.worker
    insight_report_worker = monitoring.insight_report_worker
    standard_validation_worker = monitoring.standard_validation_worker
    start_worker = monitoring.start_worker

    @router.get("/api/health")
    def health() -> dict[str, Any]:
        with database.connect() as connection:
            connection.execute("SELECT 1").fetchone()
        workers = {
            "listing": _worker_health(worker, start_worker),
            "insight_report": _worker_health(insight_report_worker, start_worker),
            "classification_standard_validation": _worker_health(
                standard_validation_worker,
                start_worker,
            ),
        }
        worker_statuses = {item["status"] for item in workers.values()}
        worker_status = (
            "unavailable"
            if "unavailable" in worker_statuses
            else "degraded"
            if "degraded" in worker_statuses
            else "ok"
        )
        payload = {
            "status": "ok" if worker_status == "ok" else "degraded",
            "database": "ok",
            "worker": worker_status,
            "workers": workers,
            "time": utc_now(),
        }
        if worker_status == "unavailable":
            raise HTTPException(status_code=503, detail=payload)
        return payload


def _register_system_status_route(
    router: APIRouter,
    database: Database,
    settings: Settings,
    monitoring: _MonitoringDependencies,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]
    task_service = monitoring.task_service
    worker = monitoring.worker
    start_worker = monitoring.start_worker

    @router.get("/api/system/status")
    def system_status(user: User) -> dict[str, Any]:
        with database.connect() as connection:
            task_counts = {
                row["status"]: row["count"]
                for row in connection.execute(
                    "SELECT status, COUNT(*) AS count FROM tasks GROUP BY status"
                ).fetchall()
            }
            pending_reviews = connection.execute(
                """
                SELECT COUNT(*) AS count FROM review_records
                WHERE workflow_status = 'pending' AND batch_id IS NOT NULL
                """
            ).fetchone()["count"]
            pending_review_batches = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM review_batches AS batch
                WHERE batch.status = 'draft'
                  AND EXISTS (
                      SELECT 1
                      FROM review_records AS record
                      WHERE record.batch_id = batch.id
                        AND record.workflow_status = 'pending'
                  )
                """
            ).fetchone()["count"]
        warnings = []
        if settings.bootstrap_password == "change-me-now":
            warnings.append("仍在使用默认初始密码")
        if not settings.encryption_key:
            warnings.append("仍在使用开发环境加密密钥")
        running_segments = task_service.running_count(str(user["id"]))
        return {
            "user": user,
            "task_counts": task_counts,
            "pending_reviews": pending_reviews,
            "pending_review_batches": pending_review_batches,
            "my_running_tasks": running_segments,
            "my_running_segments": running_segments,
            "worker_concurrency": settings.task_workers,
            "worker_status": (
                "ok" if not start_worker or worker.is_alive else "unavailable"
            ),
            "warnings": warnings,
        }
