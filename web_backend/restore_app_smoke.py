from __future__ import annotations

import json
import sys
import time
from http.cookiejar import CookieJar
from secrets import token_hex, token_urlsafe
from threading import Thread
from typing import Any
from urllib.request import HTTPCookieProcessor, OpenerDirector, Request, build_opener

import uvicorn

from web_backend.common import new_id
from web_backend.database import Database
from web_backend.security import hash_password, utc_now
from web_backend.settings import Settings


def _request_json(
    opener: OpenerDirector,
    url: str,
    payload: dict[str, str] | None = None,
) -> Any:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload else None,
        headers={"Content-Type": "application/json"} if payload else {},
    )
    with opener.open(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError("应用接口状态异常")
        return json.load(response)


def _wait_for_server(server: uvicorn.Server, thread: Thread) -> int:
    for _ in range(300):
        if server.started:
            sockets = server.servers[0].sockets
            if sockets:
                return int(sockets[0].getsockname()[1])
        if not thread.is_alive():
            break
        time.sleep(0.1)
    raise RuntimeError("恢复后的应用未能启动")


def smoke_restored_app() -> None:
    settings = Settings.from_env()
    if (
        settings.data_dir.name != "runtime"
        or not settings.data_dir.parent.name.startswith(".restore-drill-")
        or settings.database_path != settings.data_dir / "app.db"
    ):
        raise ValueError("应用演练仅允许使用隔离恢复目录")

    database = Database(settings.database_path)
    user_id = new_id("user")
    email = f"restore-drill-{token_hex(8)}@example.invalid"
    password = token_urlsafe(24)
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO users(id, email, display_name, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, email, "恢复演练账号", hash_password(password), utc_now()),
        )
        dashboard_total = int(
            connection.execute("SELECT COUNT(*) FROM analysis_dashboards").fetchone()[0]
        )

    from web_backend.app import create_app

    app = create_app(start_worker=False, settings_override=settings)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=0,
            log_level="critical",
            access_log=False,
        )
    )
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{_wait_for_server(server, thread)}"
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        health = _request_json(opener, f"{base_url}/api/health")
        if health.get("status") != "ok" or health.get("database") != "ok":
            raise RuntimeError("恢复后的应用健康检查失败")
        login = _request_json(
            opener,
            f"{base_url}/api/auth/login",
            {"email": email, "password": password},
        )
        current_user = _request_json(opener, f"{base_url}/api/auth/me")
        if login.get("id") != user_id or current_user.get("id") != user_id:
            raise RuntimeError("恢复后的应用登录检查失败")
        tasks = _request_json(opener, f"{base_url}/api/tasks")
        dashboards = _request_json(
            opener,
            f"{base_url}/api/analysis-dashboards?page=1&page_size=1",
        )
        if not isinstance(tasks, list) or not isinstance(dashboards.get("items"), list):
            raise RuntimeError("恢复后的业务列表格式异常")
        if dashboards.get("total") != dashboard_total:
            raise RuntimeError("恢复后的看板数量不一致")
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        if thread.is_alive():
            raise RuntimeError("应用演练服务未正常停止")


def main() -> int:
    try:
        smoke_restored_app()
    except Exception as exc:
        print(f"恢复后的应用检查失败：{type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
