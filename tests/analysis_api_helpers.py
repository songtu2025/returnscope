import base64
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

from test_classification_result_pool import _seed_result_context

from return_semantics.exporter import export_results
from web_backend.security import hash_password
from web_backend.settings import Settings

if TYPE_CHECKING:
    from fastapi import FastAPI

SYNTHETIC_EMAIL = "one@example.com"
SYNTHETIC_PASSWORD = "Synthetic-metrics-round13!"


def analysis_app(root: Path) -> "FastAPI":
    context = _seed_result_context(root)
    workbook = root / "synthetic-results.xlsx"
    export_results(workbook, context.dataset, context.results, context.taxonomy)
    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE tasks SET title='合成数据验收任务', status='completed',
                result_file_path=?, result_version=1,
                completed_at='2026-08-12T00:00:00+00:00'
            WHERE id='task-1'
            """,
            (str(workbook),),
        )
        connection.execute(
            """
            UPDATE task_segments SET status='completed', result_file_path=?,
                result_version=1 WHERE id='segment-1'
            """,
            (str(workbook),),
        )
        connection.execute(
            """
            UPDATE users SET password_hash=?, display_name='合成验收用户'
            WHERE id='user-1'
            """,
            (hash_password(SYNTHETIC_PASSWORD),),
        )
    settings = Settings(
        data_dir=root,
        database_path=root / "app.db",
        session_days=1,
        task_workers=1,
        bootstrap_email="bootstrap@example.invalid",
        bootstrap_name="合成验收",
        bootstrap_password="synthetic-bootstrap-round13",
        encryption_key=base64.urlsafe_b64encode(b"0" * 32).decode(),
        secure_cookies=False,
        public_web_url="http://127.0.0.1:18133",
    )
    # 显式使用隔离配置，避免加载本机业务配置；模型工作器不启动。
    with patch.object(Settings, "from_env", return_value=settings):
        from web_backend.app import create_app

        app = create_app(start_worker=False, settings_override=settings)
    return app
