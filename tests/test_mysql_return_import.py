from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pymysql
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from test_classification_result_pool import _seed_result_context
from test_return_import_flow import _return_row

from return_semantics.data import RETURN_STORE_COLUMN, SOURCE_ORIGIN_COLUMN
from web_backend import dataset_service as dataset_module
from web_backend import mysql_return_service as mysql_module
from web_backend.api_schemas import MySQLReturnImportRequest
from web_backend.dataset_service import DatasetService
from web_backend.mysql_return_service import FIELD_LABELS, MySQLReturnService
from web_backend.routers.datasets import create_dataset_router
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


def test_filters_are_parameters_and_end_date_includes_whole_day(source):
    service, cursor, connect, payload = source
    payload.sku = "SKU' OR 1=1 --"
    payload.date_from = date(2026, 8, 1)
    payload.date_to = date(2026, 8, 31)
    query, values = service._query(connect.return_value, payload)
    assert payload.sku not in query
    assert "`return_date` >= %s" in query
    assert "`return_date` < %s" in query
    assert values == [date(2026, 8, 1), date(2026, 9, 1), payload.sku]
    assert "sale_return_order" in query
    assert cursor.execute.call_args.args[1] == (
        "jijia_sync_isolated_20260827",
        "sale_return_order",
    )


@pytest.mark.parametrize(
    "problem", ["unknown_column", "missing_comment", "missing_store", "reversed_dates"]
)
def test_invalid_mapping_and_filters_never_query_return_rows(source, problem):
    service, cursor, _, payload = source
    if problem == "unknown_column":
        payload.mapping["sku"] = "sku`; DROP TABLE sale_return_order; --"
    elif problem == "missing_comment":
        payload.mapping.pop("customer-comments")
    elif problem == "missing_store":
        payload.mapping.pop(RETURN_STORE_COLUMN)
    else:
        payload.date_from = date(2026, 9, 2)
        payload.date_to = date(2026, 9, 1)
    with pytest.raises(ValueError):
        service.preview(payload)
    assert not any(
        "FROM `sale_return_order`" in call.args[0]
        for call in cursor.execute.call_args_list
    )


def test_fixed_store_and_optional_fields_are_bound_values(source):
    service, _, connect, payload = source
    payload.mapping[RETURN_STORE_COLUMN] = ""
    payload.mapping["fnsku"] = ""
    payload.default_store = "测试店铺:US"
    payload.store = "测试店铺:US"
    query, values = service._query(connect.return_value, payload)
    assert "%s AS `店铺/站点`" in query
    assert "%s AS `fnsku`" in query
    assert values == ["", "测试店铺:US", "测试店铺:US", "测试店铺:US"]


def test_preview_reports_over_limit_without_creating_dataset(source):
    service, cursor, _, payload = source
    columns = cursor.fetchall.return_value
    cursor.fetchall.side_effect = [columns, [_return_row("O-1", "偏小")]]
    cursor.fetchone.return_value = {"total": 3}
    before = len(service.datasets.list("returns"))
    preview = service.preview(payload)
    assert preview["over_limit"] is True
    assert preview["row_count"] == 3
    assert len(preview["rows"]) == 1
    assert len(service.datasets.list("returns")) == before


def test_import_freezes_data_reuses_duplicates_and_records_source(source, monkeypatch):
    service, cursor, _, payload = source
    inspect = MagicMock(wraps=dataset_module.inspect_file)
    monkeypatch.setattr(dataset_module, "inspect_file", inspect)
    rows = [_return_row("MYSQL-1", "数据库评论，偏小")]
    cursor.__iter__.side_effect = lambda: iter(rows)
    result = service.import_returns(payload, "user-1")
    assert inspect.call_count == 1
    assert result["dataset"]["usage_scope"] == "task_input"
    version = service.datasets.version_file(result["dataset"]["id"])
    snapshot = Path(version["file_path"])
    assert "数据库评论，偏小" in snapshot.read_text(encoding="utf-8-sig")
    repeated = service.import_returns(payload, "user-1")
    assert repeated["duplicate"] is True
    assert repeated["version_id"] == result["version_id"]
    rows[0]["customer-comments"] = "源数据后来改变"
    assert "源数据后来改变" not in snapshot.read_text(encoding="utf-8-sig")
    with service.datasets.database.connect() as connection:
        audit = connection.execute(
            "SELECT after_json FROM audit_logs WHERE action = 'import_mysql_returns'"
        ).fetchall()
    assert len(audit) == 2
    assert "sale_return_order" in audit[0]["after_json"]
    assert service.settings.mysql_password not in audit[0]["after_json"]
    assert not list((service.settings.data_dir / "tmp").glob("mysql_*.csv"))


def test_mysql_import_keeps_source_id_in_snapshot(source):
    service, cursor, _, payload = source
    cursor.fetchall.return_value = [
        {"name": key.replace("-", "_"), "type": "varchar"} for key in FIELD_LABELS
    ] + [{"name": "id", "type": "bigint"}]
    row = _return_row("O-1", "偏小")
    row[SOURCE_ORIGIN_COLUMN] = "12345"
    cursor.__iter__.side_effect = lambda: iter([row])

    result = service.import_returns(payload, "user-1")
    version = service.datasets.version_file(result["dataset"]["id"])
    snapshot = Path(version["file_path"]).read_text(encoding="utf-8-sig")
    assert SOURCE_ORIGIN_COLUMN in snapshot.splitlines()[0]
    assert "12345" in snapshot


@pytest.mark.parametrize("problem", ["empty", "too_many", "empty_store"])
def test_failed_import_cleans_temporary_file_and_creates_no_dataset(source, problem):
    service, cursor, _, payload = source
    rows = [_return_row("MYSQL-1", "偏小")]
    if problem == "empty":
        rows = []
    elif problem == "too_many":
        rows *= 3
    else:
        rows[0][RETURN_STORE_COLUMN] = ""
    cursor.__iter__.return_value = iter(rows)
    before = len(service.datasets.list("returns"))
    with pytest.raises(ValueError):
        service.import_returns(payload, "user-1")
    assert len(service.datasets.list("returns")) == before
    assert not list((service.settings.data_dir / "tmp").glob("mysql_*.csv"))


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


def test_same_store_across_accounts_keeps_paired_ids(source, monkeypatch):
    service, _, connection, payload = source
    columns = [{"name": value} for value in payload.mapping.values()]
    columns.append({"name": "market_store"})
    mappings = [
        {"jijia_account_id": 1, "market_id": 10, "store": "同名:US"},
        {"jijia_account_id": 2, "market_id": 20, "store": "同名:US"},
    ]
    monkeypatch.setattr(
        service,
        "_metadata_rows",
        lambda _conn, key: columns if key == "columns" else mappings,
    )
    payload.mapping[RETURN_STORE_COLUMN] = "market_store"
    payload.store = "同名:US"
    sql, values = service._query(connection.return_value, payload, count_only=True)
    assert sql.count("source.jijia_account_id = %s AND source.market_id = %s") == 2
    assert values == ["同名:US", 1, 10, 2, 20]
    payload.store = "不存在的店铺"
    sql, _ = service._query(connection.return_value, payload, count_only=True)
    assert "0 = 1" in sql
