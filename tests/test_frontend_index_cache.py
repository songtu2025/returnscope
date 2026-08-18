from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import web_backend.app as app_module
from web_backend.settings import Settings


def test_frontend_index_is_revalidated_and_reads_latest_script(
    tmp_path: Path,
    monkeypatch,
) -> None:
    static_dir = tmp_path / "web-prototype" / "dist" / "client"
    static_dir.mkdir(parents=True)
    index_path = static_dir / "index.html"
    first_script = f"index-{uuid4().hex}.js"
    latest_script = f"index-{uuid4().hex}.js"
    index_path.write_text(
        f'<meta content="__SITE_ORIGIN__"><script src="/assets/{first_script}"></script>',
        encoding="utf-8",
    )
    monkeypatch.setattr(app_module, "PROJECT_ROOT", tmp_path)
    runtime_dir = tmp_path / "runtime"
    settings = Settings(
        data_dir=runtime_dir,
        database_path=runtime_dir / "app.db",
        session_days=14,
        task_workers=1,
        bootstrap_email="admin@example.com",
        bootstrap_name="管理员",
        bootstrap_password="test-password-123",
        encryption_key=Fernet.generate_key().decode("ascii"),
        secure_cookies=False,
    )
    app = app_module.create_app(start_worker=False, settings_override=settings)

    with TestClient(app) as client:
        first = client.get("/")
        assert first.status_code == 200
        assert first.headers["cache-control"] == "no-cache"
        assert first_script in first.text
        assert "http://testserver" in first.text

        index_path.write_text(
            f'<meta content="__SITE_ORIGIN__"><script src="/assets/{latest_script}"></script>',
            encoding="utf-8",
        )
        refreshed = client.get("/")
        direct_index = client.get("/index.html")

    assert refreshed.headers["cache-control"] == "no-cache"
    assert latest_script in refreshed.text
    assert first_script not in refreshed.text
    assert direct_index.headers["cache-control"] == "no-cache"
    assert latest_script in direct_index.text
