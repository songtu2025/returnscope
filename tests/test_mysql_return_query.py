from datetime import date

import pytest
from mysql_return_helpers import source as source

from return_semantics.data import RETURN_STORE_COLUMN


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


@pytest.mark.parametrize(
    ("problem", "message"),
    [("unknown_target", "未知的目标字段"), ("max_date", "结束日期超出支持范围")],
)
def test_query_rejects_unknown_target_and_overflow_date(source, problem, message):
    service, cursor, _, payload = source
    if problem == "unknown_target":
        payload.mapping["未知字段"] = "sku"
    else:
        payload.date_to = date.max
    with pytest.raises(ValueError, match=message):
        service.preview(payload)
    assert not any(
        "FROM `sale_return_order`" in call.args[0]
        for call in cursor.execute.call_args_list
    )
