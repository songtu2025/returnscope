from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from web_backend.agent_runner import AgentRunner
from web_backend.analysis_service import AnalysisService
from web_backend.application_runtime import (
    AuthRuntime,
    _create_current_user,
    _create_database,
    _create_lifespan,
    _create_task_service,
)
from web_backend.auth_service import AuthService
from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.classification_standard_validation_service import (
    ClassificationStandardValidationService,
)
from web_backend.classification_standard_validation_worker import (
    ClassificationStandardValidationWorker,
)
from web_backend.config_service import ConfigService
from web_backend.dashboard_service import DashboardService
from web_backend.data_quality_service import DataQualityService
from web_backend.database import Database
from web_backend.dataset_service import DatasetService
from web_backend.insight_report_service import InsightReportService
from web_backend.insight_report_worker import InsightReportWorker
from web_backend.mail_service import MailSender, create_mail_sender
from web_backend.model_preference_service import ModelPreferenceService
from web_backend.operations_service import AuditLogService, WorkbenchService
from web_backend.request_timing import RequestTimingMiddleware
from web_backend.review_service import ReviewService
from web_backend.routers.accounts import create_account_router
from web_backend.routers.auth_actions import (
    AuthActionLimiters,
    create_auth_action_router,
)
from web_backend.routers.classification_results import (
    create_classification_result_router,
)
from web_backend.routers.classification_standards import (
    create_classification_standard_router,
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
)
from web_backend.settings import PROJECT_ROOT, Settings
from web_backend.worker import TaskWorker

AuthRuntime.__module__ = __name__


def _create_auth_runtime(
    database: Database,
    settings: Settings,
    mail_sender_override: MailSender | None,
) -> AuthRuntime:
    session_service = SessionService(database, settings.session_days)
    mail_sender = mail_sender_override or create_mail_sender(settings)
    return AuthRuntime(
        session_service=session_service,
        mail_sender=mail_sender,
        auth_service=AuthService(database, settings, mail_sender, session_service),
        account_login_limiter=LoginAttemptLimiter(5, 15 * 60),
        address_login_limiter=LoginAttemptLimiter(30, 15 * 60),
        action_limiters=AuthActionLimiters(
            reset_account=LoginAttemptLimiter(3, 15 * 60),
            reset_address=LoginAttemptLimiter(10, 15 * 60),
            invitation_admin=LoginAttemptLimiter(
                settings.invitation_send_limit_per_admin,
                settings.invitation_send_window_seconds,
            ),
            invitation_recipient=LoginAttemptLimiter(
                settings.invitation_send_limit_per_recipient,
                settings.invitation_send_window_seconds,
            ),
        ),
    )


def _create_validation_executor(config_service: ConfigService) -> ThreadPoolExecutor:
    config_service.recover_validation_runs()
    return ThreadPoolExecutor(
        max_workers=2,
        thread_name_prefix="model-validation",
    )


def _mount_frontend(app: FastAPI) -> None:
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


def create_app(
    start_worker: bool = True,
    settings_override: Settings | None = None,
    mail_sender_override: MailSender | None = None,
) -> FastAPI:
    settings = settings_override or Settings.from_env()
    database = _create_database(settings)
    secret_box = SecretBox(settings.encryption_key)
    auth_runtime = _create_auth_runtime(database, settings, mail_sender_override)
    dummy_password_hash = hash_password("invalid-password-only")
    dataset_service = DatasetService(database, settings)
    config_service = ConfigService(database, secret_box)
    model_preference_service = ModelPreferenceService(database)
    validation_executor = _create_validation_executor(config_service)
    analysis_service = AnalysisService(database)
    result_service = ClassificationResultService(database)
    standard_service = ClassificationStandardService(database)
    dashboard_service = DashboardService(database)
    insight_report_service = InsightReportService(
        database,
        dashboard_service,
        config_service,
    )
    data_quality_service = DataQualityService(database)
    workbench_service = WorkbenchService(database)
    audit_log_service = AuditLogService(database)
    review_service = ReviewService(database, result_service, standard_service)
    runner = AgentRunner(
        database,
        settings,
        config_service,
        result_service,
        standard_service,
    )
    task_service = _create_task_service(database, standard_service, runner)
    worker = TaskWorker(database, runner, settings.task_workers)
    insight_report_worker = InsightReportWorker(insight_report_service)
    standard_validation_service = ClassificationStandardValidationService(
        database,
        standard_service,
        runner,
    )
    standard_validation_worker = ClassificationStandardValidationWorker(
        standard_validation_service
    )

    lifespan = _create_lifespan(
        start_worker,
        worker,
        insight_report_worker,
        standard_validation_worker,
        validation_executor,
    )
    app = FastAPI(
        title="用户语义分析智能体",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.add_middleware(RequestTimingMiddleware)

    current_user = _create_current_user(auth_runtime.session_service)
    app.include_router(
        create_account_router(
            database=database,
            settings=settings,
            session_service=auth_runtime.session_service,
            account_login_limiter=auth_runtime.account_login_limiter,
            address_login_limiter=auth_runtime.address_login_limiter,
            dummy_password_hash=dummy_password_hash,
            task_service=task_service,
            worker=worker,
            insight_report_worker=insight_report_worker,
            standard_validation_worker=standard_validation_worker,
            start_worker=start_worker,
            current_user=current_user,
        )
    )
    app.include_router(
        create_auth_action_router(
            auth_service=auth_runtime.auth_service,
            settings=settings,
            limiters=auth_runtime.action_limiters,
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
            standard_service=standard_service,
            current_user=current_user,
        )
    )
    app.include_router(
        create_classification_standard_router(
            service=standard_service,
            validation_service=standard_validation_service,
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

    _mount_frontend(app)

    app.state.settings = settings
    app.state.database = database
    app.state.auth_service = auth_runtime.auth_service
    app.state.mail_sender = auth_runtime.mail_sender
    app.state.worker = worker
    app.state.insight_report_service = insight_report_service
    app.state.insight_report_worker = insight_report_worker
    app.state.standard_validation_service = standard_validation_service
    app.state.standard_validation_worker = standard_validation_worker
    return app


app = create_app()
