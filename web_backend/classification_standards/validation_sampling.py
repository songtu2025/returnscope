from __future__ import annotations

from typing import Any, TypeVar

from web_backend.common import json_value
from web_backend.database import Database

_BucketKey = TypeVar("_BucketKey", str, tuple[str, ...])


def _take_bucket_samples(
    buckets: dict[_BucketKey, list[dict[str, Any]]],
    sample_size: int,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    keys = sorted(buckets, key=lambda key: (-len(buckets[key]), key))
    while len(output) < sample_size and any(buckets.values()):
        for key in keys:
            if buckets[key] and len(output) < sample_size:
                output.append(buckets[key].pop(0))
    return output


class ClassificationStandardValidationSamplingMixin:
    database: Database

    @staticmethod
    def _round_robin_samples(
        items: list[dict[str, Any]],
        sample_size: int,
        *,
        bucket_fields: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        buckets: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for item in sorted(items, key=lambda value: value["classification_key"]):
            key = tuple(str(item[field]) for field in bucket_fields)
            buckets.setdefault(key, []).append(item)
        return _take_bucket_samples(buckets, sample_size)

    def _sample(
        self,
        result_version_id: str,
        sample_size: int,
    ) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT unit.classification_key, unit.comment, unit.reason,
                       unit.classification_json, unit.quality_status,
                       MIN(COALESCE(record.category_a, '')) AS category_a,
                       MIN(COALESCE(record.category_b, '')) AS category_b
                FROM classification_units unit
                LEFT JOIN classification_result_records record
                  ON record.result_version_id = unit.result_version_id
                 AND record.classification_key = unit.classification_key
                WHERE unit.result_version_id = ?
                  AND TRIM(COALESCE(unit.comment, '')) != ''
                  AND unit.quality_status != 'excluded'
                GROUP BY unit.classification_key, unit.comment, unit.reason,
                         unit.classification_json, unit.quality_status
                ORDER BY unit.classification_key
                """,
                (result_version_id,),
            ).fetchall()
        buckets: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            item = dict(row)
            classification = json_value(item.pop("classification_json"), {})
            item["baseline"] = classification
            labels = classification.get("primary_label_codes", [])
            bucket = str(labels[0]) if labels else "__NO_PRIMARY_LABEL__"
            buckets.setdefault(bucket, []).append(item)
        return _take_bucket_samples(buckets, sample_size)
