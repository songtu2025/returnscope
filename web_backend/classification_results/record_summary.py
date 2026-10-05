"""汇总结果版本的评论、事实、事件与主题统计。"""

from __future__ import annotations

from sqlite3 import Row
from typing import TYPE_CHECKING, Any

from return_semantics.schemas import TaxonomyConfig
from return_semantics.taxonomy_hierarchy import label_path
from web_backend.classification_result_payload import (
    PAGE_SIZE_DEFAULT,
    _prepare_classification_payload,
)
from web_backend.common import json_value
from web_backend.database import Database

_SummaryRows = tuple[list[Row], list[Row], list[Row], list[Row]]
_SummarySemantics = tuple[
    dict[str, dict[str, int]], dict[str, int], dict[str, dict[str, Any]], int, int
]


class ClassificationResultRecordSummaryMixin:
    database: Database
    if TYPE_CHECKING:

        def get(self, version_id: str) -> dict[str, Any]: ...

        def taxonomy(self, version_id: str) -> TaxonomyConfig | None: ...

        def drilldown(
            self,
            version_id: str,
            group_by: str,
            *,
            page: int = 1,
            page_size: int = PAGE_SIZE_DEFAULT,
            **filters: str | None,
        ) -> dict[str, Any]: ...

    def summary(self, version_id: str) -> dict[str, Any]:
        self.get(version_id)
        taxonomy = self.taxonomy(version_id)
        quality_rows, status_rows, problem_rows, unit_rows = self._summary_rows(
            version_id
        )
        (
            disposition_counts,
            comment_status_counts,
            topic_counts,
            fact_count,
            event_count,
        ) = self._summary_semantics(unit_rows, taxonomy)
        source_record_count = sum((int(row["record_count"] or 0) for row in unit_rows))
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
            "quality": self._summary_counted_rows(quality_rows),
            "processing_statuses": self._summary_counted_rows(status_rows),
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
            "top_problems": self._summary_problems(problem_rows, taxonomy),
            "hierarchy_problems": self.drilldown(version_id, "category")["items"],
        }

    def _summary_rows(self, version_id: str) -> _SummaryRows:
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
        return (quality_rows, status_rows, problem_rows, unit_rows)

    def _summary_semantics(
        self, unit_rows: list[Row], taxonomy: TaxonomyConfig | None
    ) -> _SummarySemantics:
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
                disposition, {"comment_count": 0, "record_count": 0}
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
                self._add_summary_topic(topic_counts, topic, comment_weight)
        return (
            disposition_counts,
            comment_status_counts,
            topic_counts,
            fact_count,
            event_count,
        )

    @staticmethod
    def _add_summary_topic(
        topic_counts: dict[str, dict[str, Any]],
        topic: dict[str, Any],
        comment_weight: int,
    ) -> None:
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

    @staticmethod
    def _summary_counted_rows(rows: list[Row]) -> list[dict[str, Any]]:
        return [
            {**dict(row), "comment_count": int(row["record_count"])} for row in rows
        ]

    @staticmethod
    def _summary_problems(
        problem_rows: list[Row], taxonomy: TaxonomyConfig | None
    ) -> list[dict[str, Any]]:
        return [
            {
                **dict(row),
                "comment_count": int(row["unit_count"]),
                "label_path": label_path(taxonomy, row["label_code"])
                if taxonomy
                else [],
            }
            for row in problem_rows
        ]
