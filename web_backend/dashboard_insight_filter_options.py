"""复用看板基础范围生成逐级收窄的产品候选项。"""

from __future__ import annotations

from web_backend.dashboard_insight_scope import InsightQueryScope
from web_backend.request_timing import timed_stage


@timed_stage("insight_filter_options")
def _collect_filter_options(
    scope: InsightQueryScope,
    reuse_option_records: bool,
    *,
    listing: str | None = None,
    product_name: str | None = None,
) -> dict[str, list[str]]:
    columns = {
        "listings": "r.listing",
        "product_names": "r.product_name",
        "product_skus": "r.product_sku",
    }
    ancestors = {
        "listings": {},
        "product_names": {"listing": listing},
        "product_skus": {"listing": listing, "product_name": product_name},
    }
    table = (
        scope.records_table if reuse_option_records else "classification_result_records"
    )
    where_sql = "1=1" if reuse_option_records else scope.option_where
    params = [] if reuse_option_records else list(scope.option_params)
    materialization = "NOT MATERIALIZED" if reuse_option_records else "MATERIALIZED"
    queries = []
    for key, column in columns.items():
        conditions = [f"{column} IS NOT NULL", f"TRIM({column}) <> ''"]
        for field, value in ancestors[key].items():
            if value and value.strip():
                conditions.append(f"r.{field} = ?")
                params.append(value.strip())
        queries.append(
            f"SELECT DISTINCT '{key}' AS kind, {column} AS value "
            f"FROM option_records r WHERE {' AND '.join(conditions)}"
        )
    # 基础范围仍只读取一次；日期、原因和当前 SKU 不反向限制上级选项。
    rows = scope.connection.execute(
        f"""
        WITH option_records AS {materialization} (
            SELECT r.listing, r.product_name, r.product_sku
            FROM {table} r WHERE {where_sql}
        )
        {" UNION ALL ".join(queries)}
        ORDER BY kind, value COLLATE NOCASE ASC
        """,
        tuple(params),
    ).fetchall()
    options: dict[str, list[str]] = {key: [] for key in columns}
    for row in rows:
        options[str(row["kind"])].append(str(row["value"]))
    return options
