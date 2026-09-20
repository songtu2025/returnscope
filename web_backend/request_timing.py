from __future__ import annotations

import logging
import time
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

performance_logger = logging.getLogger("uvicorn.error.performance")


class RequestTimingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        response_started = False

        async def send_with_timing(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                duration_ms = (time.perf_counter() - started) * 1000
                MutableHeaders(scope=message).append(
                    "Server-Timing",
                    f"app;dur={duration_ms:.2f}",
                )
                self._log_request(scope, int(message["status"]), duration_ms)
            await send(message)

        try:
            await self.app(scope, receive, send_with_timing)
        except Exception:
            if not response_started:
                duration_ms = (time.perf_counter() - started) * 1000
                performance_logger.exception(
                    "request_performance method=%s route=%s status=500 "
                    "duration_ms=%.2f",
                    scope.get("method", ""),
                    self._route_path(scope),
                    duration_ms,
                )
            raise

    @staticmethod
    def _route_path(scope: Scope) -> str:
        route: Any = scope.get("route")
        return str(getattr(route, "path", scope.get("path", "")))

    @classmethod
    def _log_request(cls, scope: Scope, status: int, duration_ms: float) -> None:
        path = str(scope.get("path", ""))
        if not path.startswith("/api/") or path == "/api/health":
            return
        performance_logger.info(
            "request_performance method=%s route=%s status=%s duration_ms=%.2f",
            scope.get("method", ""),
            cls._route_path(scope),
            status,
            duration_ms,
        )
