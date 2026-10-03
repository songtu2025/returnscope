from __future__ import annotations

from typing import TYPE_CHECKING, Any

from return_semantics.schemas import TaxonomyConfig
from web_backend.classification_result_payload import (
    PAGE_SIZE_DEFAULT,
    REVIEW_DISPOSITIONS,
    _unknown_disposition,
    prepare_semantic_record,
)
from web_backend.classification_results.record_drilldowns import (
    ClassificationResultRecordDrilldownsMixin,
)
from web_backend.classification_results.record_summary import (
    ClassificationResultRecordSummaryMixin,
)
from web_backend.common import json_value
from web_backend.database import Database
from web_backend.result_hierarchy import enrich_record, feedback_group_key_sql


class _ClassificationResultRecords(
    ClassificationResultRecordDrilldownsMixin,
    ClassificationResultRecordSummaryMixin,
):
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
        group_key = feedback_group_key_sql("r")
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
        value = prepare_semantic_record(value, taxonomy)
        classification = value["classification"]
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
