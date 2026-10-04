from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import uvicorn
from test_review_http_lifecycle import (
    SYNTHETIC_PASSWORD,
    _create_dashboard_report,
    _login,
    _publish_operation,
    _published_snapshot,
    _request,
    _write_snapshot,
)
from test_review_http_lifecycle import http_lifecycle as http_lifecycle
from test_review_http_lifecycle import lifecycle as lifecycle

from scripts.smoke_web_business import BusinessScope, check_business
from scripts.smoke_web_production import SmokeClient


@contextmanager
def _serve_application(http_lifecycle: SimpleNamespace) -> Iterator[str]:
    # 使用系统分配的端口和正式 ASGI 生命周期，避免替换 HTTP 传输与 Cookie。
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    app = http_lifecycle.open_client().app
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="critical", access_log=False, ws="none")
    )
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [listener]}, daemon=True
    )
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, "隔离 HTTP 服务未启动"
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive(), "隔离 HTTP 服务未停止"


def _run_cli(base_url: str, scope: BusinessScope) -> subprocess.CompletedProcess[str]:
    arguments = [
        sys.executable,
        "-m",
        "scripts.smoke_web_business",
        "--base-url",
        base_url,
        "--email",
        "one@example.com",
        "--allow-http",
    ]
    for name, value in asdict(scope).items():
        arguments.extend(["--" + name.replace("_", "-"), value])
    return subprocess.run(
        arguments,
        cwd=Path(__file__).resolve().parents[1],
        env=os.environ
        | {"WEBAPP_SMOKE_PASSWORD": SYNTHETIC_PASSWORD, "PYTHONUTF8": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )


def _assert_cli_success(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.splitlines() == [
        "[通过] 登录与安全会话",
        "[通过] 分类结果版本、分页与统计",
        "[通过] 人工复核批次与派生版本",
        "[通过] 驾驶舱版本、来源与统计",
        "[通过] 报告状态与证据版本",
        "[通过] 退出登录",
        "业务关联验收通过",
    ]


@pytest.mark.parametrize("operation", ["remove", "add"])
def test_business_cli_preserves_published_data_across_application_restart(
    http_lifecycle: SimpleNamespace, operation: str
) -> None:
    state = http_lifecycle.state
    with http_lifecycle.open_client() as client:
        _login(client)
        derived, base_snapshot = _publish_operation(client, state, operation)
        ids = _create_dashboard_report(client, state, derived)
        snapshot = _published_snapshot(client, ids)
    scope = BusinessScope(
        result_version_id=ids["result_id"],
        review_batch_id=state.batch["id"],
        dashboard_id=ids["dashboard_id"],
        dashboard_version_id=ids["dashboard_version_id"],
        report_id=ids["report_id"],
    )
    before = _write_snapshot(state.database)
    with _serve_application(http_lifecycle) as base_url:
        _assert_cli_success(_run_cli(base_url, scope))
        wrong_scope = replace(
            scope, dashboard_version_id=state.dashboard["version"]["version_id"]
        )
        failed = _run_cli(base_url, wrong_scope)
        assert failed.returncode != 0
        assert failed.stderr.strip() == (
            "[失败] 验收驾驶舱必须只引用指定结果且不设置业务筛选"
        )
        assert failed.stdout.splitlines() == [
            "[通过] 登录与安全会话",
            "[通过] 分类结果版本、分页与统计",
            "[通过] 人工复核批次与派生版本",
        ]
        anonymous = SmokeClient(base_url)
        with pytest.raises(RuntimeError, match="返回 401"):
            check_business(anonymous, scope)
        anonymous.login("one@example.com", SYNTHETIC_PASSWORD)
        anonymous.logout()
        with pytest.raises(RuntimeError, match="返回 401"):
            check_business(anonymous, scope)
    assert _write_snapshot(state.database) == before
    _assert_restarted_business(http_lifecycle, ids, snapshot, base_snapshot)
    with _serve_application(http_lifecycle) as restarted_url:
        _assert_cli_success(_run_cli(restarted_url, scope))
    assert _write_snapshot(state.database) == before


def _assert_restarted_business(
    http_lifecycle: SimpleNamespace,
    ids: dict[str, str],
    snapshot: dict,
    base_snapshot: dict,
) -> None:
    state = http_lifecycle.state
    base_path = f"/api/classification-results/{state.base['version_id']}/records"
    with http_lifecycle.open_client() as restarted:
        _login(restarted)
        assert _published_snapshot(restarted, ids) == snapshot
        assert _request(restarted, "GET", base_path) == base_snapshot
        batch_path = f"/api/review-batches/{state.batch['id']}"
        batch = _request(restarted, "GET", batch_path)
        _request(
            restarted,
            "POST",
            f"{batch_path}/publish",
            409,
            json={"expected_revision": batch["revision"], "reason": "合成重复发布"},
        )
