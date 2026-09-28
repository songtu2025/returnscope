from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event, Lock
from time import sleep

import pytest

from web_backend import dashboard_service
from web_backend.dashboard_service import DashboardService
from web_backend.database import Database


def test_parallel_identical_insights_share_one_calculation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = DashboardService(Database(tmp_path / "app.db"))
    barrier = Barrier(6)
    entered = Event()
    release = Event()
    calls: list[str | None] = []
    calls_lock = Lock()

    def fake_build_insights(database, dashboard_id, version_id, options):
        with calls_lock:
            calls.append(options.problem)
        entered.set()
        assert release.wait(10)
        return {"problem": options.problem}

    monkeypatch.setattr(dashboard_service, "build_insights", fake_build_insights)

    def request(problem: str | None):
        barrier.wait(timeout=10)
        return service.insights("dashboard", "version", problem=problem)

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(request, None) for _ in range(5)]
        futures.append(executor.submit(request, "other"))
        assert entered.wait(10)
        sleep(0.1)
        release.set()
        results = [future.result(timeout=10) for future in futures]

    assert results == [{"problem": None}] * 5 + [{"problem": "other"}]
    assert len({id(result) for result in results}) == 6
    results[0]["extra"] = True
    assert "extra" not in results[1]
    assert sorted(str(value) for value in calls) == ["None", "other"]
    assert service.insights("dashboard", "version") == {"problem": None}
    assert len(calls) == 3


def test_failed_insight_calculation_can_be_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = DashboardService(Database(tmp_path / "app.db"))
    barrier = Barrier(2)
    entered = Event()
    release = Event()
    calls = 0

    def fail(database, dashboard_id, version_id, options):
        nonlocal calls
        calls += 1
        entered.set()
        assert release.wait(10)
        raise ValueError("查询失败")

    monkeypatch.setattr(dashboard_service, "build_insights", fail)

    def request():
        barrier.wait(timeout=10)
        return service.insights("dashboard", "version")

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(request) for _ in range(2)]
        assert entered.wait(10)
        sleep(0.1)
        release.set()
        for future in futures:
            with pytest.raises(ValueError, match="查询失败"):
                future.result(timeout=10)
    assert calls == 1

    with pytest.raises(ValueError, match="查询失败"):
        service.insights("dashboard", "version")
    assert calls == 2
