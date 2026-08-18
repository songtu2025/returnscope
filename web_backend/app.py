from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Annotated, Any, AsyncIterator

from fastapi import Cookie, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from web_backend.agent_runner import AgentRunner
from web_backend.analysis_service import AnalysisService
from web_backend.classification_result_service import ClassificationResultService
from web_backend.common import new_id
from web_backend.config_service import ConfigService
from web_backend.dashboard_service import DashboardService
from web_backend.data_quality_service import DataQualityService
from web_backend.database import Database
from web_backend.dataset_service import DatasetService
from web_backend.insight_report_service import InsightReportService
from web_backend.insight_report_worker import InsightReportWorker
from web_backend.model_preference_service import ModelPreferenceService
from web_backend.operations_service import AuditLogService, WorkbenchService
from web_backend.review_service import ReviewService
from web_backend.routers.accounts import SESSION_COOKIE, create_account_router
from web_backend.routers.classification_results import (
    create_classification_result_router,
)
from web_backend.routers.dashboards import create_dashboard_router
from web_backend.routers.datasets import create_dataset_router
from web_backend.routers.insight_reports import create_insight_report_router
from web_backend.routers.model_preferences import create_model_preference_router
from web_backend.routers.models import create_model_router
from web_backend.routers.operations import create_operations_router
from web_backend.routers.reviews import create_review_router
from web_backend.routers.tasks import create_task_router
from web_backend.security import (
    LoginAttemptLimiter,
    SecretBox,
    SessionService,
    hash_password,
    utc_now,
)
from web_backend.settings import PROJECT_ROOT, Settings
from web_backend.task_service import TaskService
from web_backend.worker import TaskWorker


def _bootstrap_user(database: Database, settings: Settings) -> None:
    with database.transaction(immediate=True) as connection:
        exists = connection.execute(
            "SELECT id FROM users WHERE email = ?",
            (settings.bootstrap_email,),
        ).fetchone()
        if exists is None:
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
        else:
            connection.execute(
                "UPDATE users SET is_admin = 1 WHERE email = ?",
                (settings.bootstrap_email,),
            )


def create_app(
    start_worker: bool = True,
    settings_override: Settings | None = None,
) -> FastAPI:
    settings = settings_override or Settings.from_env()
    settings.ensure_directories()
    database = Database(settings.database_path)
    database.initialize()
    _bootstrap_user(database, settings)
    secret_box = SecretBox(settings.encryption_key)
    session_service = SessionService(database, settings.session_days)
    account_login_limiter = LoginAttemptLimiter(5, 15 * 60)
    address_login_limiter = LoginAttemptLimiter(30, 15 * 60)
    dummy_password_hash = hash_password("invalid-password-only")
    dataset_service = DatasetService(database, settings)
    config_service = ConfigService(database, secret_box)
    model_preference_service = ModelPreferenceService(database)
    config_service.recover_validation_runs()
    validation_executor = ThreadPoolExecutor(
        max_workers=2,
        thread_name_prefix="model-validation",
    )
    analysis_service = AnalysisService(database)
    result_service = ClassificationResultService(database)
    dashboard_service = DashboardService(database)
    insight_report_service = InsightReportService(
        database,
        dashboard_service,
        config_service,
    )
    data_quality_service = DataQualityService(database)
    workbench_service = WorkbenchService(database)
    audit_log_service = AuditLogService(database)
    review_service = ReviewService(database, result_service)
    runner = AgentRunner(database, settings, config_service, result_service)
    task_service = TaskService(
        database,
        result_publisher=runner.retry_result_publish,
    )
    worker = TaskWorker(database, runner, settings.task_workers)
    insight_report_worker = InsightReportWorker(insight_report_service)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if start_worker:
            worker.start()
            insight_report_worker.start()
        yield
        if start_worker:
            worker.stop()
            insight_report_worker.stop()
        validation_executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(
        title="退货语义分析智能体",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )

    def current_user(
        session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    ) -> dict[str, Any]:
        user = session_service.resolve(session_token)
        if user is None:
            raise HTTPException(status_code=401, detail="请先登录")
        return user

    app.include_router(
        create_account_router(
            database=database,
            settings=settings,
            session_service=session_service,
            account_login_limiter=account_login_limiter,
            address_login_limiter=address_login_limiter,
            dummy_password_hash=dummy_password_hash,
            task_service=task_service,
            worker=worker,
            start_worker=start_worker,
            current_user=current_user,
        )
    )
    app.include_router(
        create_dataset_router(
            dataset_service=dataset_service,
            settings=settings,
            current_user=current_user,
        )
    )
    app.include_router(
        create_model_router(
            config_service=config_service,
            validation_executor=validation_executor,
            current_user=current_user,
        )
    )
    app.include_router(
        create_model_preference_router(
            service=model_preference_service,
            current_user=current_user,
        )
    )
    app.include_router(
        create_task_router(
            task_service=task_service,
            analysis_service=analysis_service,
            current_user=current_user,
        )
    )
    app.include_router(
        create_review_router(
            review_service=review_service,
            database=database,
            current_user=current_user,
        )
    )
    app.include_router(
        create_classification_result_router(
            result_service=result_service,
            current_user=current_user,
        )
    )
    app.include_router(
        create_dashboard_router(
            dashboard_service=dashboard_service,
            current_user=current_user,
        )
    )
    app.include_router(
        create_insight_report_router(
            service=insight_report_service,
            current_user=current_user,
        )
    )
    app.include_router(
        create_operations_router(
            workbench_service=workbench_service,
            data_quality_service=data_quality_service,
            audit_log_service=audit_log_service,
            current_user=current_user,
        )
    )

    static_dir = PROJECT_ROOT / "web-prototype" / "dist" / "client"
    if static_dir.exists():

        @app.get("/index.html", response_class=HTMLResponse)
        @app.get("/", response_class=HTMLResponse)
        def frontend_index(request: Request) -> HTMLResponse:
            html = (static_dir / "index.html").read_text(encoding="utf-8")
            origin = str(request.base_url).rstrip("/")
            return HTMLResponse(
                html.replace("__SITE_ORIGIN__", origin),
                headers={"Cache-Control": "no-cache"},
            )

        app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")

    app.state.settings = settings
    app.state.database = database
    app.state.worker = worker
    app.state.insight_report_service = insight_report_service
    app.state.insight_report_worker = insight_report_worker
    return app


app = create_app()
