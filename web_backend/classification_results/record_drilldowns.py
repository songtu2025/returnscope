"""按分类层级、问题或商品维度下钻结果记录。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from return_semantics.taxonomy_hierarchy import label_path
from web_backend.classification_result_payload import PAGE_SIZE_DEFAULT
from web_backend.classification_results.record_filters import (
    ClassificationResultRecordFiltersMixin,
)
from web_backend.database import Database
from web_backend.result_hierarchy import feedback_group_key_sql, hierarchy_counts


class ClassificationResultRecordDrilldownsMixin(ClassificationResultRecordFiltersMixin):
    database: Database

    if TYPE_CHECKING:

        def get(self, version_id: str) -> dict[str, Any]: ...

    def drilldown(
        self,
        version_id: str,
        group_by: str,
        *,
        page: int = 1,
        page_size: int = PAGE_SIZE_DEFAULT,
        **filters: str | None,
    ) -> dict[str, Any]:
        self.get(version_id)
        if group_by not in {"category", "problem", "product_name", "product_sku"}:
            raise ValueError(
                "group_by 仅支持 category、problem、product_name、product_sku"
            )
        page, page_size = self._validate_page(page, page_size)
        where_sql, params = self._record_filters(version_id, filters)
        group_key = feedback_group_key_sql("r")
        if group_by == "category":
            taxonomy = self.taxonomy(version_id)
            with self.database.connect() as connection:
                items = (
                    hierarchy_counts(
                        connection,
                        taxonomy,
                        where_sql,
                        params,
                        feedback_groups=True,
                    )
                    if taxonomy
                    else []
                )
            return {
                "group_by": group_by,
                "items": items[(page - 1) * page_size : page * page_size],
                "total": len(items),
                "page": page,
                "page_size": page_size,
            }
        taxonomy = self.taxonomy(version_id) if group_by == "problem" else None
        if group_by == "problem":
            join_sql = """
                JOIN classification_unit_labels l
                  ON l.result_version_id = r.result_version_id
                 AND l.classification_key = r.classification_key
                 AND l.label_kind = 'problem'
            """
            group_columns = "l.label_code, l.label_name, l.label_group"
            value_columns = """
                l.label_code AS value, l.label_name AS label_name,
                l.label_group AS label_group
            """
        else:
            join_sql = ""
            column = f"r.{group_by}"
            group_columns = column
            value_columns = f"{column} AS value"
        base_sql = f"""
            FROM classification_result_records r
            {join_sql}
            WHERE {where_sql}
            GROUP BY {group_columns}
        """
        with self.database.connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM (SELECT 1 {base_sql})",
                    tuple(params),
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT {value_columns},
                       COUNT(DISTINCT {group_key}) AS record_count,
                       COUNT(DISTINCT r.classification_key) AS unit_count
                {base_sql}
                ORDER BY record_count DESC, value ASC
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "group_by": group_by,
            "items": [
                {**dict(row), "label_path": label_path(taxonomy, row["value"])}
                if taxonomy
                else dict(row)
                for row in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
