from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from fastapi.testclient import TestClient
from test_auth_flows import FakeMailSender, _settings

import web_backend.app as app_module
from web_backend.security import SESSION_COOKIE, SessionService

ROUTER_FACTORIES = (
    "create_account_router",
    "create_auth_action_router",
    "create_dataset_router",
    "create_model_router",
    "create_model_preference_router",
    "create_task_router",
    "create_review_router",
    "create_classification_result_router",
    "create_classification_standard_router",
    "create_dashboard_router",
    "create_insight_report_router",
    "create_operations_router",
)
WORKER_TYPES = (
    "TaskWorker",
    "InsightReportWorker",
    "ClassificationStandardValidationWorker",
)


@pytest.fixture
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    lifecycle = Mock()
    workers = {}
    for index, name in enumerate(WORKER_TYPES):
        worker = Mock(spec=getattr(app_module, name))
        workers[name] = Mock(return_value=worker)
        monkeypatch.setattr(app_module, name, workers[name])
        lifecycle.attach_mock(worker.start, f"start_{index}")
        lifecycle.attach_mock(worker.stop, f"stop_{index}")
    executor = Mock(spec=ThreadPoolExecutor)
    executor_factory = Mock(return_value=executor)
    monkeypatch.setattr(app_module, "ThreadPoolExecutor", executor_factory)
    lifecycle.attach_mock(executor.shutdown, "shutdown")
    initialization = Mock()
    initialization.attach_mock(executor_factory, "executor")
    recover = app_module.ConfigService.recover_validation_runs

    def tracked_recovery(service) -> None:
        initialization.recover()
        recover(service)

    monkeypatch.setattr(
        app_module.ConfigService, "recover_validation_runs", tracked_recovery
    )
    routing = Mock()
    routers = {}
    for name in ROUTER_FACTORIES:
        routers[name] = Mock(wraps=getattr(app_module, name))
        monkeypatch.setattr(app_module, name, routers[name])
        routing.attach_mock(routers[name], name)
    monkeypatch.setattr(app_module, "PROJECT_ROOT", tmp_path)
    return SimpleNamespace(
        settings=_settings(tmp_path),
        sender=FakeMailSender(),
        workers=workers,
        executor=executor,
        executor_factory=executor_factory,
        lifecycle=lifecycle,
        initialization=initialization,
        routers=routers,
        routing=routing,
    )


@pytest.fixture
def app(runtime):
    return app_module.create_app(
        start_worker=False,
        settings_override=runtime.settings,
        mail_sender_override=runtime.sender,
    )


@pytest.mark.parametrize("start_worker", [True, False])
def test_workers_follow_application_lifespan(runtime, start_worker: bool) -> None:
    app = app_module.create_app(
        start_worker=start_worker,
        settings_override=runtime.settings,
        mail_sender_override=runtime.sender,
    )
    assert runtime.lifecycle.mock_calls == []
    starts = [call.start_0(), call.start_1(), call.start_2()] if start_worker else []
    stops = [call.stop_0(), call.stop_1(), call.stop_2()] if start_worker else []
    with TestClient(app):
        assert runtime.lifecycle.mock_calls == starts
    assert runtime.lifecycle.mock_calls == [
        *starts,
        *stops,
        call.shutdown(wait=False, cancel_futures=True),
    ]
    account_dependencies = runtime.routers["create_account_router"].call_args.kwargs
    assert account_dependencies["start_worker"] is start_worker


def test_validation_recovery_precedes_executor_creation(app, runtime) -> None:
    assert runtime.initialization.mock_calls == [
        call.recover(),
        call.executor(max_workers=2, thread_name_prefix="model-validation"),
    ]
    model_dependencies = runtime.routers["create_model_router"].call_args.kwargs
    assert model_dependencies["validation_executor"] is runtime.executor


@pytest.mark.parametrize("stage", ["recover", "executor"])
def test_validation_initialization_failure_is_propagated(runtime, stage: str) -> None:
    error = RuntimeError("模拟初始化失败")
    if stage == "recover":
        runtime.initialization.recover.side_effect = error
    else:
        runtime.executor_factory.side_effect = error
    with pytest.raises(RuntimeError) as caught:
        app_module.create_app(
            settings_override=runtime.settings,
            mail_sender_override=runtime.sender,
        )
    assert caught.value is error
    if stage == "recover":
        runtime.executor_factory.assert_not_called()
    assert runtime.routing.mock_calls == []
    assert runtime.lifecycle.mock_calls == []


def test_routes_share_one_login_dependency_and_keep_registration_order(
    app, runtime
) -> None:
    assert [item[0] for item in runtime.routing.mock_calls] == list(ROUTER_FACTORIES)
    dependencies = [
        factory.call_args.kwargs["current_user"] for factory in runtime.routers.values()
    ]
    assert all(dependency is dependencies[0] for dependency in dependencies)
    assert app.title == "用户语义分析智能体"
    assert app.version == "1.0.0"
    assert app.docs_url is None
    assert app.redoc_url is None


def test_state_and_routes_reuse_the_same_runtime_instances(app, runtime) -> None:
    account = runtime.routers["create_account_router"].call_args.kwargs
    authentication = runtime.routers["create_auth_action_router"].call_args.kwargs
    reports = runtime.routers["create_insight_report_router"].call_args.kwargs
    standards = runtime.routers[
        "create_classification_standard_router"
    ].call_args.kwargs
    expected = {
        "settings": runtime.settings,
        "database": account["database"],
        "auth_service": authentication["auth_service"],
        "mail_sender": runtime.sender,
        "worker": runtime.workers["TaskWorker"].return_value,
        "insight_report_service": reports["service"],
        "insight_report_worker": runtime.workers["InsightReportWorker"].return_value,
        "standard_validation_service": standards["validation_service"],
        "standard_validation_worker": (
            runtime.workers["ClassificationStandardValidationWorker"].return_value
        ),
    }
    assert set(app.state._state) == set(expected)
    assert all(getattr(app.state, name) is value for name, value in expected.items())
    assert account["worker"] is app.state.worker
    assert account["insight_report_worker"] is app.state.insight_report_worker
    assert account["standard_validation_worker"] is app.state.standard_validation_worker
    runtime.workers["InsightReportWorker"].assert_called_once_with(reports["service"])
    runtime.workers["ClassificationStandardValidationWorker"].assert_called_once_with(
        standards["validation_service"]
    )


def test_task_planning_and_publication_share_existing_services(app, runtime) -> None:
    task = runtime.routers["create_task_router"].call_args.kwargs["task_service"]
    standards = runtime.routers[
        "create_classification_standard_router"
    ].call_args.kwargs
    runner = runtime.workers["TaskWorker"].call_args.args[1]
    assert task.database is app.state.database
    assert task.plan_service.database is app.state.database
    assert task.plan_service.standard_service is standards["service"]
    assert task.result_publisher == runner.retry_result_publish
    assert standards["validation_service"].runner is runner
    assert standards["validation_service"].standard_service is standards["service"]
    assert (
        runtime.routers["create_account_router"].call_args.kwargs["task_service"]
        is task
    )
    runtime.workers["TaskWorker"].assert_called_once_with(
        app.state.database, runner, runtime.settings.task_workers
    )


@pytest.mark.parametrize("settings_override", [True, False])
@pytest.mark.parametrize("mail_override", [True, False])
def test_settings_and_mail_overrides_are_preserved(
    runtime, monkeypatch, settings_override: bool, mail_override: bool
) -> None:
    from_env = Mock(return_value=runtime.settings)
    default_sender = FakeMailSender()
    create_sender = Mock(return_value=default_sender)
    monkeypatch.setattr(app_module.Settings, "from_env", from_env)
    monkeypatch.setattr(app_module, "create_mail_sender", create_sender)
    app = app_module.create_app(
        start_worker=False,
        settings_override=runtime.settings if settings_override else None,
        mail_sender_override=runtime.sender if mail_override else None,
    )
    assert app.state.settings is runtime.settings
    assert app.state.mail_sender is (
        runtime.sender if mail_override else default_sender
    )
    if settings_override:
        from_env.assert_not_called()
    else:
        from_env.assert_called_once_with()
    if mail_override:
        create_sender.assert_not_called()
    else:
        create_sender.assert_called_once_with(runtime.settings)


@pytest.mark.parametrize(
    ("cookies", "resolved_token"),
    [
        ({}, None),
        ({SESSION_COOKIE: "invalid"}, "invalid"),
        ({"other": "invalid"}, None),
    ],
)
def test_login_dependency_resolves_only_the_session_cookie(
    app, monkeypatch, cookies: dict[str, str], resolved_token: str | None
) -> None:
    resolve = Mock(return_value=None)
    monkeypatch.setattr(SessionService, "resolve", resolve)
    with TestClient(app, cookies=cookies) as client:
        response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "请先登录"}
    resolve.assert_called_once_with(resolved_token)


def test_authenticated_user_is_returned_unchanged(app, monkeypatch) -> None:
    user = {"id": "42", "email": "member@example.com", "is_admin": False}
    resolve = Mock(return_value=user)
    monkeypatch.setattr(SessionService, "resolve", resolve)
    with TestClient(app, cookies={SESSION_COOKIE: "valid"}) as client:
        response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json() == user
    resolve.assert_called_once_with("valid")


@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_missing_frontend_build_keeps_api_available(app, path: str) -> None:
    with TestClient(app) as client:
        assert client.get(path).status_code == 404
        assert client.get("/api/auth/me").status_code == 401


def test_static_mount_follows_api_routes(runtime, tmp_path: Path) -> None:
    static_dir = tmp_path / "web-prototype" / "dist" / "client"
    static_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("首页 __SITE_ORIGIN__", encoding="utf-8")
    (static_dir / "asset.css").write_text("body { color: green; }", encoding="utf-8")
    app = app_module.create_app(
        start_worker=False,
        settings_override=runtime.settings,
        mail_sender_override=runtime.sender,
    )
    with TestClient(app, base_url="https://example.invalid") as client:
        assert client.get("/api/auth/me").status_code == 401
        response = client.get("/")
        assert response.text == "首页 https://example.invalid"
        assert response.headers["cache-control"] == "no-cache"
        assert client.get("/asset.css").text == "body { color: green; }"
    assert app.routes[-1].name == "web"
