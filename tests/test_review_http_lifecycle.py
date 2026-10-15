from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from test_review_dashboard_report_lifecycle import lifecycle as lifecycle

from web_backend.security import SecretBox, hash_password
from web_backend.settings import Settings

SYNTHETIC_PASSWORD = "synthetic-http-test-password"


@pytest.fixture
def http_lifecycle(
    lifecycle: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> SimpleNamespace:
    settings = Settings(
        data_dir=tmp_path,
        database_path=lifecycle.database.path,
        session_days=14,
        task_workers=1,
        bootstrap_email="admin@example.test",
        bootstrap_name="合成测试管理员",
        bootstrap_password=SYNTHETIC_PASSWORD,
        encryption_key=Fernet.generate_key().decode("ascii"),
        secure_cookies=False,
    )
    with lifecycle.database.transaction() as connection:
        connection.execute(
            "UPDATE users SET password_hash = ?, is_admin = 0 WHERE id = 'user-1'",
            (hash_password(SYNTHETIC_PASSWORD),),
        )
        connection.execute(
            "UPDATE api_config_versions SET api_key_ciphertext = ?",
            (SecretBox(settings.encryption_key).encrypt("synthetic-model-key"),),
        )
    # 模块默认应用也使用隔离配置，避免首次导入读取项目环境文件。
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: settings))
    from web_backend.app import create_app

    def open_client() -> TestClient:
        app = create_app(start_worker=False, settings_override=settings)
        # 仅替换外部模型，保留正式登录、路由、服务和数据库实现。
        app.state.insight_report_service.client_factory = (
            lifecycle.reports.client_factory
        )
        return TestClient(app)

    return SimpleNamespace(state=lifecycle, open_client=open_client)


def test_direct_correction_survives_http_and_app_restart(http_lifecycle):
    state = http_lifecycle.state
    version_id = state.base["version_id"]
    record_id = state.results.record_groups(version_id)["items"][0]["record"]["id"]
    with http_lifecycle.open_client() as client:
        response = client.post(
            "/api/auth/login",
            json={"email": "one@example.com", "password": SYNTHETIC_PASSWORD},
        )
        assert response.status_code == 200
        changed = client.patch(
            f"/api/classification-results/{version_id}/records/{record_id}/semantics",
            json={"semantic_items": []},
        )
        assert changed.status_code == 200
        next_id = changed.json()["version_id"]
        assert next_id != version_id
        assert (
            client.post("/api/review-batches/none/publish", json={}).status_code == 410
        )
    with http_lifecycle.open_client() as client:
        assert (
            client.post(
                "/api/auth/login",
                json={"email": "one@example.com", "password": SYNTHETIC_PASSWORD},
            ).status_code
            == 200
        )
        assert client.get(f"/api/classification-results/{next_id}").status_code == 200
        with state.database.connect() as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM review_batches").fetchone()[0]
                == 0
            )
