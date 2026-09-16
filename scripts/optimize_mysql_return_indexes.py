"""检查或添加退货导入所需索引，不修改业务记录。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pymysql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web_backend.settings import Settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="执行缺失索引的创建")
    args = parser.parse_args()
    settings = Settings.from_env()
    if settings.mysql_table != "sale_return_order":
        raise SystemExit("此脚本仅用于 sale_return_order 数据源")
    indexes = [
        ("sale_return_order", "idx_return_date", ("return_date_time",)),
        (
            "sale_return_order",
            "idx_return_account_market_msku_date",
            ("jijia_account_id", "market_id", "msku", "return_date_time"),
        ),
        (
            "sale_return_order",
            "idx_return_account_market_date",
            ("jijia_account_id", "market_id", "return_date_time"),
        ),
        ("raw_api_data", "idx_raw_api_account", ("api_code", "jijia_account_id")),
    ]
    with pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
        charset="utf8mb4",
        autocommit=True,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION lock_wait_timeout = 5")
            for table, name, columns in indexes:
                cursor.execute(
                    "SELECT INDEX_NAME, COLUMN_NAME, SUB_PART "
                    "FROM information_schema.STATISTICS "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
                    "ORDER BY INDEX_NAME, SEQ_IN_INDEX",
                    (settings.mysql_database, table),
                )
                existing: dict[str, list[str | None]] = {}
                for index_name, column, prefix in cursor.fetchall():
                    existing.setdefault(index_name, []).append(
                        column if prefix is None else None
                    )
                if any(
                    tuple(value[: len(columns)]) == columns
                    for value in existing.values()
                ):
                    print(f"已覆盖：{table} {columns}", flush=True)
                    continue
                if name in existing:
                    raise SystemExit(f"索引 {name} 已存在但字段不一致，请检查")
                sql = (
                    f"ALTER TABLE `{table}` ADD INDEX `{name}` "
                    f"({', '.join(f'`{column}`' for column in columns)}), "
                    "ALGORITHM=INPLACE, LOCK=NONE"
                )
                print(sql, flush=True)
                if args.apply:
                    cursor.execute(sql)
                    print(f"已创建：{name}", flush=True)


if __name__ == "__main__":
    main()
