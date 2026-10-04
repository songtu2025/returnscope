from pathlib import Path
from unittest.mock import MagicMock

import pymysql
import pytest
from test_classification_result_pool import _seed_result_context

from web_backend.api_contracts.datasets import (
    MySQLReturnImportRequest,
)
from web_backend.dataset_service import DatasetService
from web_backend.mysql_return_service import FIELD_LABELS, MySQLReturnService
from web_backend.settings import Settings


@pytest.fixture
def source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    context = _seed_result_context(tmp_path)
    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "app.db",
        session_days=14,
        task_workers=1,
        bootstrap_email="test@example.com",
        bootstrap_name="测试",
        bootstrap_password="测试密码",
        encryption_key="",
        secure_cookies=False,
        mysql_user="reader",
        mysql_password="不应出现在接口中",
        mysql_max_rows=2,
    )
    datasets = DatasetService(context.database, settings)
    service = MySQLReturnService(datasets, settings)
    connection = MagicMock()
    connection.__enter__.return_value = connection
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    connection.cursor.return_value = cursor
    cursor.fetchall.return_value = [
        {"name": key.replace("-", "_"), "type": "varchar"} for key in FIELD_LABELS
    ]
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(pymysql, "connect", connect)
    payload = MySQLReturnImportRequest(
        mapping={key: key.replace("-", "_") for key in FIELD_LABELS}
    )
    return service, cursor, connect, payload
