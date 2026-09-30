from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web_backend.request_timing import RequestTimingMiddleware, timed_stage


def test_sync_route_accumulates_stages_and_keeps_requests_isolated() -> None:
    app = FastAPI()
    app.add_middleware(RequestTimingMiddleware)
    barrier = Barrier(2)

    @app.get("/api/test/{stage}")
    def measure(stage: str) -> dict[str, bool]:
        with timed_stage(stage):
            barrier.wait(timeout=5)
        with timed_stage(stage):
            pass
        return {"ok": True}

    with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda stage: client.get(f"/api/test/{stage}"), ["first", "second"]
            )
        )
    for response, own, other in zip(
        responses, ["first", "second"], ["second", "first"], strict=True
    ):
        assert response.status_code == 200
        metrics = response.headers["Server-Timing"].split(", ")
        assert len(metrics) == 2
        assert metrics[0].startswith("app;dur=")
        assert metrics[1].startswith(f"{own};dur=")
        assert other not in response.headers["Server-Timing"]
        assert float(metrics[1].split("=")[1]) >= 0


def test_failed_stage_does_not_leak_into_next_request() -> None:
    app = FastAPI()
    app.add_middleware(RequestTimingMiddleware)

    @app.get("/api/failure")
    def fail() -> None:
        with timed_stage("failed_stage"):
            raise ValueError("测试异常")

    @app.get("/api/success")
    def succeed() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        with pytest.raises(ValueError, match="测试异常"):
            client.get("/api/failure")
        response = client.get("/api/success")
    assert response.status_code == 200
    assert response.headers["Server-Timing"].startswith("app;dur=")
    assert "failed_stage" not in response.headers["Server-Timing"]
