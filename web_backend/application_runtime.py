from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any, AsyncIterator

from fastapi import Cookie, FastAPI, HTTPException

from web_backend.agent_runner import AgentRunner
from web_backend.auth_service import AuthService
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.classification_standard_validation_worker import (
    ClassificationStandardValidationWorker,
)
from web_backend.common import new_id
from web_backend.dashboards.live_sources import refresh_related_dashboards
from web_backend.database import Database
from web_backend.insight_report_worker import InsightReportWorker
from web_backend.mail_service import MailSender
from web_backend.routers.auth_actions import AuthActionLimiters
from web_backend.security import (
    SESSION_COOKIE,
    LoginAttemptLimiter,
    SessionService,
    hash_password,
    utc_now,
)
from web_backend.settings import Settings
from web_backend.task_plan_service import TaskPlanService
from web_backend.task_service import TaskService
from web_backend.worker import TaskWorker


@dataclass(frozen=True)
class AuthRuntime:
    session_service: SessionService
    mail_sender: MailSender
    auth_service: AuthService
    account_login_limiter: LoginAttemptLimiter
    address_login_limiter: LoginAttemptLimiter
    action_limiters: AuthActionLimiters


def _bootstrap_user(database: Database, settings: Settings) -> None:
    with database.transaction(immediate=True) as connection:
        exists = connection.execute(
            "SELECT id FROM users WHERE email = ?",
            (settings.bootstrap_email,),
        ).fetchone()
        user_count = int(
            connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()[
                "count"
            ]
        )
        if exists is None and user_count == 0:
            connection.execute(
                """
                INSERT INTO users(
                    id, email, display_name, password_hash, is_admin, created_at
                ) VALUES (?, ?, ?, ?, 1, ?)
                """,
                (
                    new_id("user"),
                    settings.bootstrap_email,
                    settings.bootstrap_name,
                    hash_password(settings.bootstrap_password),
                    utc_now(),
                ),
            )
        elif exists is not None:
            connection.execute(
                "UPDATE users SET is_admin = 1 WHERE email = ?",
                (settings.bootstrap_email,),
            )


def _create_database(settings: Settings) -> Database:
    settings.ensure_directories()
    database = Database(settings.database_path)
    database.initialize(production=settings.production)
    _bootstrap_user(database, settings)
    with database.transaction(immediate=True) as connection:
        refresh_related_dashboards(database, connection, None, utc_now())
    return database


def _create_task_service(
    database: Database,
    standard_service: ClassificationStandardService,
    runner: AgentRunner,
) -> TaskService:
    task_plan_service = TaskPlanService(
        database,
        standard_service=standard_service,
    )
    return TaskService(
        database,
        plan_service=task_plan_service,
        result_publisher=runner.retry_result_publish,
    )


def _create_lifespan(
    start_worker: bool,
    worker: TaskWorker,
    insight_report_worker: InsightReportWorker,
    standard_validation_worker: ClassificationStandardValidationWorker,
    validation_executor: ThreadPoolExecutor,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if start_worker:
            worker.start()
            insight_report_worker.start()
            standard_validation_worker.start()
        yield
        if start_worker:
            worker.stop()
            insight_report_worker.stop()
            standard_validation_worker.stop()
        validation_executor.shutdown(wait=False, cancel_futures=True)

    return lifespan


def _create_current_user(
    session_service: SessionService,
) -> Callable[..., dict[str, Any]]:
    def current_user(
        session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    ) -> dict[str, Any]:
        user = session_service.resolve(session_token)
        if user is None:
            raise HTTPException(status_code=401, detail="请先登录")
        return user

    return current_user
