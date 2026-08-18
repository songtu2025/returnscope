from __future__ import annotations

import argparse
import getpass
import http.cookiejar
import json
import os
import urllib.error
import urllib.request
from email.message import Message
from urllib.parse import urlparse

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=()",
    "Content-Security-Policy": "default-src 'self'",
}


def validate_base_url(value: str, allow_http: bool = False) -> str:
    base_url = value.strip().rstrip("/")
    parsed = urlparse(base_url)
    if not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("服务地址必须是完整域名，且不能包含查询参数")
    if parsed.path not in {"", "/"}:
        raise ValueError("服务地址不能包含路径")
    if parsed.scheme != "https" and not (allow_http and parsed.scheme == "http"):
        raise ValueError("生产冒烟验收必须使用 HTTPS")
    return base_url


def validate_security_headers(headers: Message) -> list[str]:
    errors = []
    for name, expected in SECURITY_HEADERS.items():
        value = headers.get(name, "")
        if expected.lower() not in value.lower():
            errors.append(f"安全响应头不正确：{name}")
    return errors


class SmokeClient:
    def __init__(self, base_url: str, timeout: int = 20) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )

    def request(
        self,
        path: str,
        method: str = "GET",
        payload: dict[str, object] | None = None,
    ) -> tuple[int, Message, bytes]:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"{method} {path} 返回 {exc.code}：{detail[:300]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"无法连接服务：{exc.reason}") from exc

    def json(
        self,
        path: str,
        method: str = "GET",
        payload: dict[str, object] | None = None,
    ) -> tuple[int, Message, object]:
        status, headers, body = self.request(path, method, payload)
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"{path} 没有返回有效 JSON") from exc
        return status, headers, value


def run_smoke(
    base_url: str,
    email: str,
    password: str,
    minimum_workers: int,
    skip_proxy_headers: bool,
    allow_system_warnings: bool,
) -> None:
    client = SmokeClient(base_url)
    status, headers, body = client.request("/")
    if status != 200 or b'id="root"' not in body:
        raise RuntimeError("前端入口没有正常返回应用页面")
    if not skip_proxy_headers:
        header_errors = validate_security_headers(headers)
        if header_errors:
            raise RuntimeError("；".join(header_errors))
    print("[通过] 前端入口与安全响应头")

    status, _headers, health = client.json("/api/health")
    if status != 200 or not isinstance(health, dict) or health.get("status") != "ok":
        raise RuntimeError("健康检查未通过")
    print("[通过] 数据库与任务执行器健康")

    status, login_headers, _login = client.json(
        "/api/auth/login",
        method="POST",
        payload={"email": email, "password": password},
    )
    cookies = "; ".join(login_headers.get_all("Set-Cookie", []))
    required_cookie_flags = ["HttpOnly", "SameSite=lax"]
    if base_url.startswith("https://"):
        required_cookie_flags.append("Secure")
    if status != 200 or any(flag not in cookies for flag in required_cookie_flags):
        raise RuntimeError("登录会话 Cookie 安全属性不完整")

    status, _headers, current_user = client.json("/api/auth/me")
    if (
        status != 200
        or not isinstance(current_user, dict)
        or current_user.get("email") != email.lower()
    ):
        raise RuntimeError("登录后身份校验失败")
    print("[通过] 登录与安全会话")

    status, _headers, system = client.json("/api/system/status")
    if status != 200 or not isinstance(system, dict):
        raise RuntimeError("系统状态读取失败")
    if system.get("worker_status") != "ok":
        raise RuntimeError("任务执行器状态异常")
    if int(system.get("worker_concurrency", 0)) < minimum_workers:
        raise RuntimeError(f"任务槽位少于 {minimum_workers}")
    warnings = system.get("warnings", [])
    if warnings and not allow_system_warnings:
        raise RuntimeError(f"系统仍有上线告警：{'；'.join(warnings)}")
    print("[通过] 并发容量与上线安全状态")

    for path in ("/api/datasets", "/api/configs", "/api/tasks"):
        status, _headers, value = client.json(path)
        if status != 200 or not isinstance(value, list):
            raise RuntimeError(f"核心接口异常：{path}")
    print("[通过] 数据、模型配置与任务接口")

    status, _headers, _body = client.request(
        "/api/auth/logout",
        method="POST",
    )
    if status != 204:
        raise RuntimeError("退出登录失败")
    print("[通过] 退出登录")


def main() -> None:
    parser = argparse.ArgumentParser(description="验收已部署的 Web 生产服务")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--minimum-workers", type=int, default=15)
    parser.add_argument("--allow-http", action="store_true")
    parser.add_argument("--skip-proxy-headers", action="store_true")
    parser.add_argument("--allow-system-warnings", action="store_true")
    args = parser.parse_args()
    try:
        base_url = validate_base_url(args.base_url, args.allow_http)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    password = os.getenv("WEBAPP_SMOKE_PASSWORD") or getpass.getpass("管理员密码：")
    try:
        run_smoke(
            base_url,
            args.email.strip().lower(),
            password,
            args.minimum_workers,
            args.skip_proxy_headers,
            args.allow_system_warnings,
        )
    except RuntimeError as exc:
        raise SystemExit(f"[失败] {exc}") from exc
    print("生产服务冒烟验收通过")


if __name__ == "__main__":
    main()
