from __future__ import annotations

from typing import TYPE_CHECKING, Any

from return_semantics.schemas import TaxonomyConfig
from return_semantics.taxonomy_hierarchy import (
    descendant_label_codes,
    label_path,
)
from web_backend.classification_result_payload import (
    PAGE_SIZE_DEFAULT,
    PAGE_SIZE_MAX,
    QUALITY_STATUSES,
    REVIEW_DISPOSITIONS,
    _prepare_classification_payload,
    _unknown_disposition,
)
from web_backend.common import json_value
from web_backend.database import Database
from web_backend.result_hierarchy import enrich_record, hierarchy_counts


class _ClassificationResultRecords:
    database: Database

    if TYPE_CHECKING:

        def get(self, version_id: str) -> dict[str, Any]: ...

        def taxonomy(self, version_id: str) -> TaxonomyConfig | None: ...

    def records(
        self,
        version_id: str,
        *,
        page: int = 1,
        page_size: int = PAGE_SIZE_DEFAULT,
        **filters: str | None,
    ) -> dict[str, Any]:
        self.get(version_id)
        page, page_size = self._validate_page(page, page_size)
        where_sql, params = self._record_filters(version_id, filters)
        select_sql = self._records_select()
        taxonomy = self.taxonomy(version_id)
        with self.database.connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM classification_result_records r "
                    f"WHERE {where_sql}",
                    tuple(params),
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                {select_sql}
                WHERE {where_sql}
                ORDER BY r.source_row ASC, r.id ASC
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "taxonomy": taxonomy.model_dump(mode="json") if taxonomy else None,
            "items": [
                self._enrich_record(self._serialize_record(dict(row)), taxonomy)
                for row in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def record_groups(
        self,
        version_id: str,
        *,
        page: int = 1,
        page_size: int = PAGE_SIZE_DEFAULT,
        **filters: str | None,
    ) -> dict[str, Any]:
        self.get(version_id)
        page, page_size = self._validate_page(page, page_size)
        where_sql, params = self._record_filters(version_id, filters)
        group_key = """
            CASE
              WHEN TRIM(COALESCE(r.order_id, '')) = ''
                OR TRIM(COALESCE(r.classification_key, '')) = ''
              THEN json_array('record', r.id)
              ELSE json_array(
                'feedback', r.store_site, r.listing, r.order_id,
                r.source_sku, r.matched_msku, r.product_sku,
                r.product_name, r.classification_key,
                r.quality_status, r.product_match_status
              )
            END
        """
        grouped_sql = f"""
            WITH filtered AS (
                SELECT r.*, {group_key} AS display_key
                FROM classification_result_records r
                WHERE {where_sql}
            ), grouped AS (
                SELECT display_key, MIN(source_row) AS first_row,
                       COUNT(*) AS member_count
                FROM filtered GROUP BY display_key
            )
        """
        with self.database.connect() as connection:
            totals = connection.execute(
                grouped_sql + "SELECT COUNT(*) AS groups, "
                "COALESCE(SUM(member_count), 0) AS sources FROM grouped",
                tuple(params),
            ).fetchone()
            rows = connection.execute(
                grouped_sql
                + """
                , selected AS (
                    SELECT display_key, first_row, member_count
                    FROM grouped
                    ORDER BY first_row, display_key
                    LIMIT ? OFFSET ?
                )
                SELECT f.*, s.member_count, u.processing_status,
                       u.problem_labels_json, u.classification_json
                FROM filtered f
                JOIN selected s ON s.display_key = f.display_key
                JOIN classification_units u
                  ON u.result_version_id = f.result_version_id
                 AND u.classification_key = f.classification_key
                ORDER BY s.first_row, f.source_row, f.id
                """,
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        taxonomy = self.taxonomy(version_id)
        groups: list[dict[str, Any]] = []
        by_key: dict[str, dict[str, Any]] = {}
        for row in rows:
            value = dict(row)
            key = str(value.pop("display_key"))
            member_count = int(value.pop("member_count"))
            member = {
                name: value[name]
                for name in (
                    "source_record_id",
                    "source_row",
                    "source_origin_id",
                    "return_date",
                    "reason",
                    "comment",
                )
            }
            group = by_key.get(key)
            if group is None:
                group = {
                    "record": self._enrich_record(
                        self._serialize_record(value), taxonomy
                    ),
                    "member_count": member_count,
                    "members": [],
                }
                by_key[key] = group
                groups.append(group)
            group["members"].append(member)
        return {
            "items": groups,
            "total": int(totals["groups"]),
            "source_total": int(totals["sources"]),
            "page": page,
            "page_size": page_size,
        }

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
        if group_by == "category":
            taxonomy = self.taxonomy(version_id)
            with self.database.connect() as connection:
                items = (
                    hierarchy_counts(connection, taxonomy, where_sql, params)
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
                SELECT {value_columns}, COUNT(r.id) AS record_count,
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

    def summary(self, version_id: str) -> dict[str, Any]:
        self.get(version_id)
        taxonomy = self.taxonomy(version_id)
        with self.database.connect() as connection:
            quality_rows = connection.execute(
                """
                SELECT quality_status, COUNT(*) AS unit_count,
                       COALESCE(SUM(record_count), 0) AS record_count
                FROM classification_units
                WHERE result_version_id = ?
                GROUP BY quality_status ORDER BY quality_status
                """,
                (version_id,),
            ).fetchall()
            status_rows = connection.execute(
                """
                SELECT processing_status, COUNT(*) AS unit_count,
                       COALESCE(SUM(record_count), 0) AS record_count
                FROM classification_units
                WHERE result_version_id = ?
                GROUP BY processing_status ORDER BY processing_status
                """,
                (version_id,),
            ).fetchall()
            problem_rows = connection.execute(
                """
                SELECT l.label_code, l.label_name, l.label_group,
                       COUNT(r.id) AS record_count,
                       COUNT(DISTINCT l.classification_key) AS unit_count
                FROM classification_unit_labels l
                JOIN classification_result_records r
                  ON r.result_version_id = l.result_version_id
                 AND r.classification_key = l.classification_key
                WHERE l.result_version_id = ? AND l.label_kind = 'problem'
                GROUP BY l.label_code, l.label_name, l.label_group
                ORDER BY record_count DESC, l.label_code ASC
                LIMIT 20
                """,
                (version_id,),
            ).fetchall()
            unit_rows = connection.execute(
                """
                SELECT classification_key, record_count, processing_status,
                       quality_status, classification_json
                FROM classification_units
                WHERE result_version_id = ?
                ORDER BY classification_key
                """,
                (version_id,),
            ).fetchall()

        disposition_counts: dict[str, dict[str, int]] = {}
        comment_status_counts: dict[str, int] = {}
        topic_counts: dict[str, dict[str, Any]] = {}
        fact_count = 0
        event_count = 0
        for row in unit_rows:
            comment_weight = int(row["record_count"] or 0)
            payload = _prepare_classification_payload(
                json_value(row["classification_json"], {}),
                taxonomy,
                str(row["processing_status"]),
            )
            disposition = str(payload["semantic_disposition"])
            disposition_count = disposition_counts.setdefault(
                disposition,
                {"comment_count": 0, "record_count": 0},
            )
            disposition_count["comment_count"] += comment_weight
            disposition_count["record_count"] += comment_weight
            comment_status = str(payload["comment_summary_status"])
            comment_status_counts[comment_status] = (
                comment_status_counts.get(comment_status, 0) + comment_weight
            )
            facts = payload["atomic_facts"]
            fact_count += len(facts) * comment_weight
            event_count += (
                len(
                    {
                        str(value["event_ref"])
                        for value in facts
                        if value.get("event_ref") not in (None, "", "UNSPECIFIED")
                    }
                )
                * comment_weight
            )
            for topic in payload["comment_conclusions"]:
                topic_code = str(topic["topic_code"])
                aggregate = topic_counts.setdefault(
                    topic_code,
                    {
                        "topic_code": topic_code,
                        "topic_name": topic["topic_name"],
                        "topic_code_path": topic["topic_code_path"],
                        "topic_path": topic["topic_path"],
                        "comment_count": 0,
                        "fact_count": 0,
                        "event_count": 0,
                        "status_counts": {},
                    },
                )
                aggregate["comment_count"] += comment_weight
                aggregate["fact_count"] += int(topic["fact_count"]) * comment_weight
                aggregate["event_count"] += int(topic["event_count"]) * comment_weight
                status = str(topic["status"])
                aggregate["status_counts"][status] = (
                    aggregate["status_counts"].get(status, 0) + comment_weight
                )
        source_record_count = sum(int(row["record_count"] or 0) for row in unit_rows)
        comment_count = source_record_count
        return {
            "version_id": version_id,
            "comment_count": comment_count,
            "total_comment_count": comment_count,
            "metrics": {
                "primary_unit": "comment",
                "comment_count": comment_count,
                "source_record_count": source_record_count,
                "fact_count": fact_count,
                "event_count": event_count,
            },
            "quality": [
                {**dict(row), "comment_count": int(row["record_count"])}
                for row in quality_rows
            ],
            "processing_statuses": [
                {**dict(row), "comment_count": int(row["record_count"])}
                for row in status_rows
            ],
            "semantic_dispositions": [
                {"semantic_disposition": disposition, **counts}
                for disposition, counts in sorted(disposition_counts.items())
            ],
            "comment_statuses": [
                {"status": status, "comment_count": count}
                for status, count in sorted(comment_status_counts.items())
            ],
            "topic_summaries": sorted(
                topic_counts.values(),
                key=lambda value: (-value["comment_count"], value["topic_code"]),
            ),
            "top_problems": [
                {
                    **dict(row),
                    "comment_count": int(row["unit_count"]),
                    "label_path": label_path(taxonomy, row["label_code"])
                    if taxonomy
                    else [],
                }
                for row in problem_rows
            ],
            "hierarchy_problems": self.drilldown(version_id, "category")["items"],
        }

    @staticmethod
    def _records_select() -> str:
        return """
            SELECT r.*, u.processing_status, u.problem_labels_json,
                   u.classification_json
            FROM classification_result_records r
            JOIN classification_units u
              ON u.result_version_id = r.result_version_id
             AND u.classification_key = r.classification_key
        """

    @staticmethod
    def _serialize_record(value: dict[str, Any]) -> dict[str, Any]:
        value["problem_labels"] = json_value(
            value.pop("problem_labels_json", None),
            [],
        )
        value["classification"] = json_value(
            value.pop("classification_json", None),
            {},
        )
        return value

    @staticmethod
    def _enrich_record(
        value: dict[str, Any],
        taxonomy: TaxonomyConfig | None,
    ) -> dict[str, Any]:
        value = enrich_record(value, taxonomy)
        classification = _prepare_classification_payload(
            value.get("classification", {}),
            taxonomy,
            str(value.get("processing_status") or ""),
            source_text=str(value.get("comment") or ""),
        )
        value["semantic_disposition"] = classification.pop("semantic_disposition")
        value["comment_summary_status"] = classification.pop("comment_summary_status")
        value["atomic_facts"] = classification.pop("atomic_facts")
        value["comment_conclusions"] = classification.pop("comment_conclusions")
        all_unknown_semantics = classification.get("unknown_semantics", [])
        value["unknown_semantics"] = [
            item
            for item in all_unknown_semantics
            if _unknown_disposition(item) in REVIEW_DISPOSITIONS
        ]
        value["ignored_semantics"] = [
            item
            for item in all_unknown_semantics
            if _unknown_disposition(item) not in REVIEW_DISPOSITIONS
        ]
        value["classification"] = classification
        value["fact_count"] = len(value["atomic_facts"])
        value["event_count"] = len(
            {
                str(fact["event_ref"])
                for fact in value["atomic_facts"]
                if fact.get("event_ref") not in (None, "", "UNSPECIFIED")
            }
        )
        return value

    def _record_filters(
        self,
        version_id: str,
        filters: dict[str, str | None],
    ) -> tuple[str, list[Any]]:
        where = ["r.result_version_id = ?"]
        params: list[Any] = [version_id]
        columns = {
            "order_id": "order_id",
            "listing": "listing",
            "source_sku": "source_sku",
            "matched_msku": "matched_msku",
            "product_sku": "product_sku",
            "asin": "asin",
            "product_name": "product_name",
        }
        for name, column in columns.items():
            value = filters.get(name)
            if value:
                where.append(f"r.{column} = ?")
                params.append(value)
        quality_status = filters.get("quality_status")
        if quality_status:
            self._validate_quality_status(quality_status)
            where.append("r.quality_status = ?")
            params.append(quality_status)
        problem = filters.get("problem")
        if problem:
            taxonomy = self.taxonomy(version_id)
            codes = descendant_label_codes(taxonomy, problem) if taxonomy else [problem]
            codes = codes or [problem]
            placeholders = ",".join("?" for _ in codes)
            where.append(
                f"""
                EXISTS (
                    SELECT 1 FROM classification_unit_labels f
                    WHERE f.result_version_id = r.result_version_id
                      AND f.classification_key = r.classification_key
                      AND f.label_kind = 'problem' AND f.label_code IN ({placeholders})
                )
                """
            )
            params.extend(codes)
        return " AND ".join(where), params

    @staticmethod
    def _validate_page(page: int, page_size: int) -> tuple[int, int]:
        if page < 1:
            raise ValueError("page 必须大于等于 1")
        if not 1 <= page_size <= PAGE_SIZE_MAX:
            raise ValueError(f"page_size 必须在 1 到 {PAGE_SIZE_MAX} 之间")
        return page, page_size

    @staticmethod
    def _validate_quality_status(value: str) -> None:
        if value not in QUALITY_STATUSES:
            raise ValueError("quality_status 不合法")
