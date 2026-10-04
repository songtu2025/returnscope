from dataclasses import replace

import pymysql
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from mysql_return_helpers import source as source

from return_semantics.data import RETURN_STORE_COLUMN, SOURCE_ORIGIN_COLUMN
from web_backend.api_contracts.datasets import (
    MySQLReturnImportRequest,
)
from web_backend.mysql_returns import metadata as mysql_module
from web_backend.routers.datasets import create_dataset_router
from web_backend.settings import Settings


def test_schema_suggests_mapping_without_exposing_credentials(source):
    service, cursor, connect, _ = source
    schema = service.schema()
    assert schema["database"] == "jijia_sync_isolated_20260827"
    assert schema["table"] == "sale_return_order"
    assert schema["mapping"]["customer-comments"] == "customer_comments"
    assert service.settings.mysql_password not in str(schema)
    assert service.settings.mysql_password not in repr(service.settings)
    assert connect.call_args.kwargs["charset"] == "utf8mb4"
    assert cursor.execute.call_args_list[0].args == ("SET TRANSACTION READ ONLY",)


def test_market_store_metadata_uses_configured_return_accounts(source):
    service, cursor, connect, _ = source
    service.settings = replace(service.settings, mysql_table="return`archive")

    service._metadata_rows(connect.return_value, "markets")

    query = cursor.execute.call_args.args[0]
    assert "FROM `return``archive`" in query
    assert "records.jijia_account_id = accounts.jijia_account_id" in query
    assert "records.api_code = 'amazon_shop_page'" in query
    assert "GROUP BY records.jijia_account_id, shops.market_id" in query
    assert "HAVING COUNT(DISTINCT shops.market_name) = 1" in query


def test_sale_return_schema_joins_real_comments_and_store_names(source):
    service, cursor, connect, _ = source
    names = [
        "id",
        "raw_data_id",
        "jijia_account_id",
        "market_id",
        "return_date_time",
        "order_id",
        "msku",
        "sku",
        "asin",
        "fnsku",
        "product_name",
        "quantity",
        "reason",
    ]
    columns = [{"name": name, "type": "varchar"} for name in names]
    raw_columns = [{"name": name} for name in ("id", "jijia_account_id", "raw_json")]
    cursor.fetchall.side_effect = [
        columns,
        raw_columns,
        [
            {"store": "测试店铺:US", "jijia_account_id": 1, "market_id": 11},
            {"store": "其他店铺:CA", "jijia_account_id": 1, "market_id": 12},
        ],
    ]
    schema = service.schema()
    assert schema["mapping"]["sku"] == "msku"
    assert schema["mapping"]["return-date"] == "return_date_time"
    assert schema["mapping"]["customer-comments"] == "raw_customer_comments"
    assert set(schema["stores"]) == {"测试店铺:US", "其他店铺:CA"}
    assert schema["mapping"][RETURN_STORE_COLUMN] == "market_store"

    payload = MySQLReturnImportRequest(
        mapping=dict(schema["mapping"]), default_store="测试店铺:US"
    )
    payload.mapping[RETURN_STORE_COLUMN] = ""
    cursor.fetchall.side_effect = [columns, raw_columns]
    with pytest.raises(ValueError, match="自动关联的店铺"):
        service._query(connect.return_value, payload)

    payload.mapping[RETURN_STORE_COLUMN] = "market_store"
    payload.store = "测试店铺:US"
    cursor.fetchall.side_effect = [columns, raw_columns]
    query, values = service._query(connect.return_value, payload)
    assert "source.`msku` AS `sku`" in query
    assert "LEFT JOIN raw_api_data AS raw ON raw.id = source.raw_data_id" in query
    assert "raw.jijia_account_id = source.jijia_account_id" in query
    assert "'$.customerComments'" in query
    assert "source.jijia_account_id = %s AND source.market_id = %s" in query
    assert "JSON_TABLE" not in query
    assert "ORDER BY source.`return_date_time`, source.id" in query
    assert f"source.id AS `{SOURCE_ORIGIN_COLUMN}`" in query
    assert values == ["测试店铺:US", 1, 11]

    count_query, count_values = service._query(
        connect.return_value, payload, count_only=True
    )
    assert "raw_api_data" not in count_query
    assert "customerComments" not in count_query
    assert "ORDER BY" not in count_query
    assert count_values == values

    payload.store = ""
    all_query, all_values = service._query(
        connect.return_value, payload, count_only=True
    )
    assert "JSON_TABLE" not in all_query
    assert "source.market_id IN (%s, %s)" in all_query
    assert "raw_api_data" not in all_query
    assert all_values == [1, 11, 12]
    all_query, all_values = service._query(connect.return_value, payload)
    assert "LEFT JOIN JSON_TABLE(%s" in all_query
    assert "markets.market_id = source.market_id" in all_query
    assert "markets.jijia_account_id = source.jijia_account_id" in all_query
    assert "其他店铺:CA" in all_values[0]


def test_api_requires_login_and_returns_sanitized_connection_error(source):
    service, _, connect, payload = source
    app = FastAPI()

    def user():
        raise HTTPException(status_code=401, detail="请先登录")

    app.include_router(create_dataset_router(service.datasets, service.settings, user))
    with TestClient(app) as client:
        for path in ("/preview", ""):
            assert (
                client.post(
                    "/api/mysql-return-imports" + path,
                    json=payload.model_dump(mode="json"),
                ).status_code
                == 401
            )
        assert client.get("/api/mysql-return-imports/schema").status_code == 401
        connect.assert_not_called()
        app.dependency_overrides[user] = lambda: {"id": "user-1"}
        connect.side_effect = pymysql.OperationalError(
            1045, service.settings.mysql_password
        )
        response = client.get("/api/mysql-return-imports/schema")
        assert response.status_code == 503
        assert "1045" in response.text
        assert service.settings.mysql_password not in response.text


def test_unconfigured_source_does_not_attempt_connection(source):
    service, _, connect, _ = source
    service.settings = replace(service.settings, mysql_user="")
    assert service.schema()["configured"] is False
    connect.assert_not_called()


def test_mysql_env_file_and_system_environment_precedence(tmp_path, monkeypatch):
    monkeypatch.setattr("web_backend.settings.PROJECT_ROOT", tmp_path)
    for key in ("USER", "PASSWORD", "DATABASE", "TABLE", "HOST", "PORT", "MAX_ROWS"):
        monkeypatch.delenv(f"WEBAPP_MYSQL_{key}", raising=False)
    (tmp_path / ".env.mysql").write_text(
        "WEBAPP_MYSQL_USER=file_user\nWEBAPP_MYSQL_PASSWORD=example_password\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("WEBAPP_MYSQL_USER", "system_user")
    settings = Settings.from_env()
    assert settings.mysql_user == "system_user"
    assert settings.mysql_password == "example_password"


def test_metadata_cache_expires_and_can_be_refreshed(source, monkeypatch):
    service, cursor, _, _ = source
    clock = [0.0]
    monkeypatch.setattr(mysql_module.time, "monotonic", lambda: clock[0])
    service.schema()
    first = cursor.fetchall.call_count
    service.schema()
    assert cursor.fetchall.call_count == first
    clock[0] = 301.0
    service.schema()
    assert cursor.fetchall.call_count == first + 1
    service.schema(refresh=True)
    assert cursor.fetchall.call_count == first + 2


@pytest.mark.parametrize(("elapsed", "expected_reads"), [(299.999, 0), (300.0, 1)])
def test_metadata_cache_uses_exact_ttl_boundary(
    source, monkeypatch, elapsed, expected_reads
):
    service, cursor, _, _ = source
    clock = [0.0]
    monkeypatch.setattr(mysql_module.time, "monotonic", lambda: clock[0])
    service.schema()
    first = cursor.fetchall.call_count
    clock[0] = elapsed
    service.schema()
    assert cursor.fetchall.call_count == first + expected_reads


def test_metadata_cache_is_independent_between_services(source):
    from web_backend.mysql_return_service import MySQLReturnService

    service, cursor, _, _ = source
    other = MySQLReturnService(service.datasets, service.settings)
    service.schema()
    first = cursor.fetchall.call_count
    other.schema()
    assert cursor.fetchall.call_count == first + 1
    other.schema(refresh=True)
    after_refresh = cursor.fetchall.call_count
    service.schema()
    assert cursor.fetchall.call_count == after_refresh
    assert service._metadata is not other._metadata
    assert service._metadata_lock is not other._metadata_lock


def test_metadata_refresh_invalidates_columns_and_markets(source):
    service, cursor, connect, _ = source
    for key in ("columns", "markets"):
        service._metadata_rows(connect.return_value, key)
    first = cursor.fetchall.call_count
    service.schema(refresh=True)
    service._metadata_rows(connect.return_value, "markets")
    assert cursor.fetchall.call_count == first + 2


def test_mysql_connection_keeps_readonly_consistent_snapshot_and_closes(source):
    service, cursor, connect, _ = source
    service.schema()
    assert [call.args[0] for call in cursor.execute.call_args_list[:2]] == [
        "SET TRANSACTION READ ONLY",
        "START TRANSACTION WITH CONSISTENT SNAPSHOT",
    ]
    connect.return_value.__exit__.assert_called_once_with(None, None, None)
