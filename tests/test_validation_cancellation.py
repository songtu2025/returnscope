from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from test_classification_standard_validations import _seed_result, _services
from test_validation_run_service import _build_harness, _create_run

from web_backend.routers.model_validation_routes import register_model_validation_routes
from web_backend.validation_cancellation import cancel_validation


def test_cancelled_model_probe_discards_late_success_and_preserves_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _build_harness(tmp_path)
    run_id = str(_create_run(harness, "config", 2)["id"])
    probe = harness.probe.test

    def delayed_probe(*args, **kwargs):
        response = probe(*args, **kwargs)
        cancel_validation(harness.database, "model", run_id, "user-1")
        return response

    monkeypatch.setattr(harness.probe, "test", delayed_probe)
    harness.service.run_validation(run_id)
    run = harness.service.get_validation_run(run_id)
    assert run is not None and run["status"] == "cancelled"
    assert harness.catalog.validation_updates == []
    assert len(harness.probe.calls) == 1
    cancel_validation(harness.database, "model", run_id, "user-1")


def test_cancelled_standard_validation_cannot_be_claimed_or_published(
    tmp_path: Path,
) -> None:
    standards, validations = _services(tmp_path)
    standard = next(
        item for item in standards.list() if item["standard_key"] == "eyewear"
    )
    source = _seed_result(standards, standard)
    draft = standards.create_draft(standard["id"], "user-1")
    content = draft["content"]
    content["labels"][0]["keywords"] = ["tight"]
    draft = standards.update_draft(
        draft["id"], draft["revision"], content, "测试取消", "user-1"
    )
    run = validations.create_run(draft["id"], draft["revision"], source, 20, "user-1")
    cancel_validation(standards.database, "standard", run["id"], "user-1")
    assert validations.claim_next() is None
    validations.run(run["id"])
    result = validations.get(run["id"])
    assert result["stage"] == "cancelled"
    assert not result["publication_ready"]
    assert result["items"] == []


def test_validation_cancel_requires_login_and_model_administrator(tmp_path: Path):
    harness = _build_harness(tmp_path)
    run_id = str(_create_run(harness, "config", 1)["id"])
    actor = {"id": "user-1", "is_admin": False}

    def current_user():
        if not actor:
            raise HTTPException(status_code=401)
        return actor

    app = FastAPI()
    router = APIRouter()
    register_model_validation_routes(
        router, SimpleNamespace(database=harness.database), current_user
    )
    app.include_router(router)
    with TestClient(app) as client:
        assert client.post(f"/api/validation-runs/{run_id}/cancel").status_code == 403
        actor.clear()
        assert client.post(f"/api/validation-runs/{run_id}/cancel").status_code == 401
        actor.update(id="user-1", is_admin=True)
        assert client.post(f"/api/validation-runs/{run_id}/cancel").status_code == 200
