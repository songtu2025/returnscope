from __future__ import annotations

import threading
from types import SimpleNamespace

import web_backend.agent_runner as agent_runner_module
from web_backend.agent_runner import AgentRunner


def test_get_cache_does_not_rebuild_existing_cache(tmp_path, monkeypatch) -> None:
    created_paths = []

    class FakeJsonlCache:
        def __init__(self, path) -> None:
            created_paths.append(path)

    monkeypatch.setattr(agent_runner_module, "JsonlCache", FakeJsonlCache)
    runner = AgentRunner.__new__(AgentRunner)
    runner.settings = SimpleNamespace(data_dir=tmp_path)
    runner._caches = {}
    runner._caches_lock = threading.Lock()

    first = runner._get_cache("config-1")
    second = runner._get_cache("config-1")

    assert first is second
    assert created_paths == [tmp_path / "cache" / "config-1.jsonl"]
