from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from config_service_helpers import (
    _create_version,
    _database,
    _secret_box,
    _table_counts,
)

from web_backend.config_service import ConfigService


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"base_url": "ftp://example.com", "primary_model": ""},
            "Base URL 必须是有效的 HTTP 或 HTTPS 地址",
        ),
        (
            {"base_url": "http://example.com", "primary_model": ""},
            "非本地 API 必须使用 HTTPS",
        ),
        (
            {"primary_model": " ", "primary_effort": "invalid"},
            "主模型不能为空",
        ),
        (
            {"primary_effort": "invalid", "cheap_effort": "invalid"},
            "主模型推理强度 仅支持 low、medium、high",
        ),
        (
            {"cheap_effort": "invalid", "secondary_effort": "invalid"},
            "低成本模型推理强度 仅支持 low、medium、high",
        ),
        (
            {"secondary_effort": "invalid", "cheap_audit_percent": -1},
            "二次复核模型推理强度 仅支持 low、medium、high",
        ),
        (
            {"cheap_audit_percent": -1, "requests_per_minute": 0},
            "低成本模型抽检比例必须在 0 到 100 之间",
        ),
        (
            {"requests_per_minute": 0, "max_workers": 0},
            "每分钟请求数必须在 1 到 10000 之间",
        ),
        (
            {"max_workers": 0, "timeout_seconds": 0},
            "单任务并发必须在 1 到 16 之间",
        ),
        (
            {"timeout_seconds": 0, "change_note": ""},
            "请求超时必须在 5 到 600 秒之间",
        ),
        (
            {
                "change_note": " ",
                "models": [
                    {"model_key": "duplicate"},
                    {"model_key": "duplicate"},
                ],
            },
            "模型列表中存在重复的模型 ID",
        ),
        (
            {
                "models": [
                    {"model_key": "duplicate"},
                    {"model_key": "duplicate"},
                ]
            },
            "模型列表中存在重复的模型 ID",
        ),
    ],
)
def test_create_version_preserves_validation_order(
    tmp_path: Path,
    overrides: dict[str, Any],
    message: str,
) -> None:
    database = _database(tmp_path)
    service = ConfigService(database, _secret_box())

    with pytest.raises(ValueError) as error:
        _create_version(service, **overrides)

    assert str(error.value) == message
    assert _table_counts(database) == {
        "api_connections": 0,
        "api_models": 0,
        "api_config_versions": 0,
        "audit_logs": 0,
    }


def test_create_version_accepts_numeric_boundaries(tmp_path: Path) -> None:
    database = _database(tmp_path)
    service = ConfigService(database, _secret_box())

    lower = _create_version(
        service,
        name="下边界接入",
        cheap_audit_percent=0,
        requests_per_minute=1,
        max_workers=1,
        timeout_seconds=5,
    )
    upper = _create_version(
        service,
        name="上边界接入",
        cheap_audit_percent=100,
        requests_per_minute=10000,
        max_workers=16,
        timeout_seconds=600,
    )

    assert (
        lower["cheap_audit_percent"],
        lower["requests_per_minute"],
        lower["max_workers"],
        lower["timeout_seconds"],
    ) == (0, 1, 1, 5)
    assert (
        upper["cheap_audit_percent"],
        upper["requests_per_minute"],
        upper["max_workers"],
        upper["timeout_seconds"],
    ) == (100, 10000, 16, 600)
