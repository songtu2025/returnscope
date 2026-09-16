from __future__ import annotations

import hashlib
import json
from io import BytesIO
from typing import Any

import pandas as pd

from return_semantics.data import ReturnDataset
from return_semantics.exporter import REVIEW_STATUSES
from return_semantics.schemas import (
    ProcessingStatus,
    TaxonomyConfig,
    ValidatedClassification,
)
from return_semantics.taxonomy_hierarchy import (
    descendant_label_codes,
    label_path,
    label_path_codes,
)
from web_backend.common import json_text, json_value, new_id
from web_backend.database import Database
from web_backend.result_hierarchy import (
    enrich_record,
    hierarchy_counts,
    result_taxonomy,
)
from web_backend.result_state import result_delivery_state
from web_backend.security import utc_now

QUALITY_STATUSES = {"ready", "review_required", "unusable", "excluded"}
SEMANTIC_DISPOSITIONS = {
    "MAPPED",
    "EXPECTED_ABSTENTION",
    "EVIDENCE_ONLY",
    "TAXONOMY_GAP",
    "MAPPING_UNCERTAIN",
    "OUT_OF_SCOPE",
}
REVIEW_DISPOSITIONS = {"TAXONOMY_GAP", "MAPPING_UNCERTAIN"}
CONFIRMED_STATEMENT_TYPES = {"EXPERIENCE", "EVALUATION", "REPORTED"}
PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 200


class ClassificationResultNotFound(ValueError):
    pass


class ResultPublicationError(RuntimeError):
    pass


class ResultPublicationConflict(ResultPublicationError):
    pass


def _nullable_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _classification_quality(
    result: ValidatedClassification,
    semantic_disposition: str | None = None,
) -> str:
    if result.status == ProcessingStatus.MODEL_ERROR:
        return "unusable"
    if semantic_disposition in REVIEW_DISPOSITIONS:
        return "review_required"
    if semantic_disposition in {
        "EXPECTED_ABSTENTION",
        "EVIDENCE_ONLY",
        "OUT_OF_SCOPE",
    }:
        return "ready"
    if result.status.value in REVIEW_STATUSES:
        return "review_required"
    return "ready"


def _unknown_disposition(value: dict[str, Any]) -> str:
    disposition = str(value.get("disposition") or "").strip().upper()
    return disposition if disposition in SEMANTIC_DISPOSITIONS else "MAPPING_UNCERTAIN"


def _classification_disposition(
    payload: dict[str, Any],
    processing_status: str,
) -> str:
    dispositions = {
        _unknown_disposition(value)
        for value in payload.get("unknown_semantics", [])
        if isinstance(value, dict)
    }
    if "TAXONOMY_GAP" in dispositions:
        return "TAXONOMY_GAP"
    if "MAPPING_UNCERTAIN" in dispositions:
        return "MAPPING_UNCERTAIN"
    if payload.get("semantic_units"):
        return "MAPPED"
    if "EXPECTED_ABSTENTION" in dispositions:
        return "EXPECTED_ABSTENTION"
    if "EVIDENCE_ONLY" in dispositions:
        return "EVIDENCE_ONLY"
    if "OUT_OF_SCOPE" in dispositions:
        return "OUT_OF_SCOPE"
    if processing_status == ProcessingStatus.NO_TEXT_EVIDENCE.value:
        return "EXPECTED_ABSTENTION"
    return "MAPPED"


def _fact_id_by_label(payload: dict[str, Any]) -> dict[str, str]:
    candidates: dict[str, set[str]] = {}
    for mapping in payload.get("fact_mappings", []):
        if not isinstance(mapping, dict):
            continue
        fact_id = str(mapping.get("fact_id") or "").strip()
        if not fact_id:
            continue
        for label_code in mapping.get("label_codes", []):
            candidates.setdefault(str(label_code), set()).add(fact_id)
    return {
        label_code: next(iter(fact_ids))
        for label_code, fact_ids in candidates.items()
        if len(fact_ids) == 1
    }


def _normalize_semantic_facts(
    payload: dict[str, Any],
    taxonomy: TaxonomyConfig | None,
) -> list[dict[str, Any]]:
    facts = {
        str(value.get("fact_id")): value
        for value in payload.get("extracted_facts", [])
        if isinstance(value, dict) and value.get("fact_id")
    }
    fact_ids_by_label = _fact_id_by_label(payload)
    normalized: list[dict[str, Any]] = []
    for source in payload.get("semantic_units", []):
        if not isinstance(source, dict):
            continue
        unit = dict(source)
        label_code = str(unit.get("label_code") or "")
        fact_id = str(
            unit.get("fact_id") or fact_ids_by_label.get(label_code) or ""
        ).strip()
        fact = facts.get(fact_id, {})
        unit["fact_id"] = fact_id or None
        for field in (
            "actor_ref",
            "source_ref",
            "experiencer_ref",
            "product_ref",
            "variant_ref",
            "event_ref",
            "reference_basis",
            "statement_type",
            "fact_role",
            "operation",
            "condition",
            "causal_attribution",
            "causal_attribution_reason",
            "decision_reason",
            "context_fact_ids",
        ):
            fact_value = fact.get(field)
            if unit.get(field) in (None, "", "UNSPECIFIED") and fact_value not in (
                None,
                "",
            ):
                unit[field] = fact_value
        unit["condition"] = unit.get("condition") or ""
        unit["evidence_source"] = str(
            unit.get("evidence_source") or fact.get("evidence_source") or "UNKNOWN"
        )
        unit.setdefault("fact_role", "CONCLUSION")
        unit.setdefault("causal_attribution", "UNKNOWN")
        unit.setdefault("causal_attribution_reason", "")
        unit.setdefault("decision_reason", "")
        unit.setdefault("context_fact_ids", [])
        if taxonomy:
            unit["label_code_path"] = label_path_codes(taxonomy, label_code)
            unit["label_path"] = label_path(taxonomy, label_code)
        else:
            unit.setdefault("label_code_path", [])
            unit.setdefault("label_path", [])
        normalized.append(unit)
    return normalized


def _topic_identity(
    taxonomy: TaxonomyConfig | None,
    label_code: str,
) -> tuple[str, str, list[str], list[str]]:
    if taxonomy is None:
        return label_code, label_code, [], []
    label = next((value for value in taxonomy.labels if value.code == label_code), None)
    if label is None:
        return label_code, label_code, [], []
    code_path = label_path_codes(taxonomy, label_code)
    name_path = label_path(taxonomy, label_code)
    if taxonomy.structure_version == 2 and len(code_path) > 1:
        return code_path[-2], name_path[-2], code_path[:-1], name_path[:-1]
    topic_code = label.group or label.code
    topic_name = label.group or label.name
    return topic_code, topic_name, [topic_code], [topic_name]


def _is_confirmed_fact(unit: dict[str, Any]) -> bool:
    if str(unit.get("assertion") or "AFFIRMED") != "AFFIRMED":
        return False
    statement_type = str(unit.get("statement_type") or "")
    return not statement_type or statement_type in CONFIRMED_STATEMENT_TYPES


def _scope_key(unit: dict[str, Any]) -> tuple[str, ...] | None:
    values = tuple(
        str(unit.get(field) or "").strip()
        for field in (
            "actor_ref",
            "product_ref",
            "event_ref",
            "operation",
            "part",
            "condition",
        )
    )
    return values if all(values) and "UNSPECIFIED" not in values else None


def _unit_fact_ids(unit: dict[str, Any]) -> list[str]:
    values = [
        str(value).strip() for value in unit.get("fact_ids", []) if str(value).strip()
    ]
    fact_id = str(unit.get("fact_id") or "").strip()
    if fact_id:
        values.insert(0, fact_id)
    return list(dict.fromkeys(values))


def _topic_summaries(
    facts: list[dict[str, Any]],
    taxonomy: TaxonomyConfig | None,
    relations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    topics: dict[str, dict[str, Any]] = {}
    for fact in facts:
        label_code = str(fact.get("label_code") or "")
        topic_code, topic_name, code_path, name_path = _topic_identity(
            taxonomy, label_code
        )
        topic = topics.setdefault(
            topic_code,
            {
                "topic_code": topic_code,
                "topic_name": topic_name,
                "topic_code_path": code_path,
                "topic_path": name_path,
                "facts": [],
            },
        )
        topic["facts"].append(fact)

    summaries: list[dict[str, Any]] = []
    for topic_code in sorted(topics):
        topic = topics[topic_code]
        facts_for_topic = topic.pop("facts")
        confirmed = [value for value in facts_for_topic if _is_confirmed_fact(value)]
        sentiments = {
            str(value.get("sentiment") or "")
            for value in confirmed
            if value.get("sentiment")
        }
        label_codes = {
            str(value["label_code"])
            for value in facts_for_topic
            if value.get("label_code")
        }
        related_types = {
            str(relation.get("relation_type") or "")
            for relation in relations or []
            if isinstance(relation, dict)
            and label_codes.intersection(
                str(value) for value in relation.get("label_codes", [])
            )
        }
        if "CONFLICT" in related_types:
            status = "CONFLICT"
        elif "MIXED" in related_types:
            status = "MIXED"
        elif not confirmed or not sentiments.intersection({"POSITIVE", "NEGATIVE"}):
            status = "NO_CONFIRMED"
        elif {"POSITIVE", "NEGATIVE"}.issubset(sentiments):
            positive_scopes = {
                scope
                for value in confirmed
                if value.get("sentiment") == "POSITIVE"
                if (scope := _scope_key(value)) is not None
            }
            negative_scopes = {
                scope
                for value in confirmed
                if value.get("sentiment") == "NEGATIVE"
                if (scope := _scope_key(value)) is not None
            }
            status = "CONFLICT" if positive_scopes & negative_scopes else "MIXED"
        elif "NEGATIVE" in sentiments:
            status = "NEGATIVE"
        else:
            status = "POSITIVE"
        fact_ids = [
            fact_id for value in facts_for_topic for fact_id in _unit_fact_ids(value)
        ]
        event_ids = {
            str(value["event_ref"])
            for value in facts_for_topic
            if value.get("event_ref") not in (None, "", "UNSPECIFIED")
        }
        summaries.append(
            {
                **topic,
                "status": status,
                "supporting_fact_ids": list(dict.fromkeys(fact_ids)),
                "label_codes": sorted(label_codes),
                "fact_count": len(facts_for_topic),
                "event_count": len(event_ids),
            }
        )
    return summaries


def _comment_summary_status(
    payload: dict[str, Any],
    summaries: list[dict[str, Any]],
) -> str:
    summary = payload.get("comment_summary")
    if isinstance(summary, dict):
        status = str(summary.get("status") or "")
        is_explicit = status != "NO_CONFIRMED" or any(
            summary.get(field)
            for field in ("fact_ids", "positive_label_codes", "negative_label_codes")
        )
        if is_explicit and status in {
            "POSITIVE",
            "NEGATIVE",
            "MIXED",
            "CONFLICT",
            "NO_CONFIRMED",
        }:
            return status
    statuses = {str(value["status"]) for value in summaries}
    if "CONFLICT" in statuses:
        return "CONFLICT"
    if "MIXED" in statuses or {"POSITIVE", "NEGATIVE"}.issubset(statuses):
        return "MIXED"
    if "NEGATIVE" in statuses:
        return "NEGATIVE"
    if "POSITIVE" in statuses:
        return "POSITIVE"
    return "NO_CONFIRMED"


def _prepare_classification_payload(
    payload: dict[str, Any],
    taxonomy: TaxonomyConfig | None,
    processing_status: str,
    *,
    include_api_fields: bool = True,
) -> dict[str, Any]:
    normalized = dict(payload)
    unknown_semantics = []
    for source in normalized.get("unknown_semantics", []):
        if not isinstance(source, dict):
            continue
        unknown = dict(source)
        unknown["disposition"] = _unknown_disposition(unknown)
        unknown_semantics.append(unknown)
    normalized["unknown_semantics"] = unknown_semantics
    facts = _normalize_semantic_facts(normalized, taxonomy)
    if include_api_fields:
        for fact in facts:
            fact["fact_text_zh"] = str(fact.get("opinion") or "")
            fact["original_evidence"] = str(fact.get("evidence") or "")
            fact["object_ref"] = str(fact.get("product_ref") or "CURRENT")
            fact["usage_task"] = str(fact.get("operation") or "")
            fact["scenario"] = str(fact.get("condition") or "")
            fact["certainty"] = str(fact.get("assertion") or "AFFIRMED")
    normalized["semantic_units"] = facts
    normalized["semantic_disposition"] = _classification_disposition(
        normalized, processing_status
    )
    summaries = _topic_summaries(
        facts,
        taxonomy,
        normalized.get("semantic_relations", []),
    )
    comment_status = _comment_summary_status(normalized, summaries)
    current_summary = normalized.get("comment_summary")
    summary_is_default = isinstance(current_summary, dict) and (
        str(current_summary.get("status") or "") == "NO_CONFIRMED"
        and not any(
            current_summary.get(field)
            for field in ("fact_ids", "positive_label_codes", "negative_label_codes")
        )
    )
    if not isinstance(current_summary, dict) or summary_is_default:
        normalized["comment_summary"] = {
            "status": comment_status,
            "fact_ids": list(
                dict.fromkeys(
                    fact_id for fact in facts for fact_id in _unit_fact_ids(fact)
                )
            ),
            "positive_label_codes": sorted(
                {
                    str(fact["label_code"])
                    for fact in facts
                    if fact.get("sentiment") == "POSITIVE" and fact.get("label_code")
                }
            ),
            "negative_label_codes": sorted(
                {
                    str(fact["label_code"])
                    for fact in facts
                    if fact.get("sentiment") == "NEGATIVE" and fact.get("label_code")
                }
            ),
        }
    if include_api_fields:
        normalized["atomic_facts"] = facts
        normalized["comment_conclusions"] = summaries
        normalized["comment_summary_status"] = comment_status
    return normalized


def _version_quality(qualities: list[str]) -> str:
    if qualities and all(value == "unusable" for value in qualities):
        return "unusable"
    if any(value != "ready" for value in qualities):
        return "review_required"
    return "ready"


class ClassificationResultService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def publish_v1(
        self,
        *,
        task_id: str,
        segment_id: str,
        dataset: ReturnDataset,
        results: dict[str, ValidatedClassification],
        taxonomy: TaxonomyConfig,
        segment_status: str,
        progress_total: int,
        model_calls: int,
        cache_hits: int,
        checkpoint_path: str,
        legacy_result_version: int,
        model_failures: int = 0,
    ) -> dict[str, Any]:
        prepared = self._prepare_publication(dataset, results, taxonomy)
        now = utc_now()
        conflict: str | None = None
        try:
            with self.database.transaction(immediate=True) as connection:
                task = connection.execute(
                    """
                    SELECT id, dataset_version_id, product_version_id,
                           owner_id, store, listing
                    FROM tasks WHERE id = ?
                    """,
                    (task_id,),
                ).fetchone()
                segment = connection.execute(
                    "SELECT * FROM task_segments WHERE id = ? AND task_id = ?",
                    (segment_id, task_id),
                ).fetchone()
                if task is None or segment is None:
                    raise ValueError("任务或 Listing 片段不存在")

                content_hash = self._content_hash(
                    str(task["dataset_version_id"]),
                    str(task["product_version_id"]),
                    prepared["units"],
                    prepared["records"],
                )
                existing = connection.execute(
                    """
                    SELECT v.* FROM classification_result_versions v
                    WHERE v.source_segment_id = ? AND v.version_no = 1
                    """,
                    (segment_id,),
                ).fetchone()
                if existing is not None:
                    if str(existing["content_hash"]) == content_hash:
                        return self._get_version_with_connection(
                            connection,
                            str(existing["id"]),
                        )
                    conflict = "Listing 片段 v1 已发布且内容哈希不同，拒绝覆盖"
                    connection.execute(
                        """
                        UPDATE task_segments
                        SET result_publish_error = ?, revision = revision + 1
                        WHERE id = ?
                        """,
                        (conflict, segment_id),
                    )
                    connection.execute(
                        """
                        INSERT INTO task_events(
                            task_id, event_type, stage, message,
                            data_json, created_at
                        ) VALUES (?, 'result_publish_conflict', '生成结果',
                                  ?, ?, ?)
                        """,
                        (
                            task_id,
                            conflict,
                            json_text(
                                {
                                    "segment_id": segment_id,
                                    "existing_content_hash": existing["content_hash"],
                                    "incoming_content_hash": content_hash,
                                }
                            ),
                            now,
                        ),
                    )
                else:
                    result_id = new_id("classification_result")
                    version_id = new_id("classification_version")
                    quality_status = _version_quality(
                        [str(value["quality_status"]) for value in prepared["units"]]
                    )
                    connection.execute(
                        """
                        INSERT INTO classification_results(
                            id, source_task_id, source_segment_id,
                            dataset_version_id, product_version_id,
                            store_site, listing, agent_key, agent_family,
                            logic_version, taxonomy_version,
                            model_policy_version, standard_version_id,
                            claims_version, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            result_id,
                            task_id,
                            segment_id,
                            task["dataset_version_id"],
                            task["product_version_id"],
                            prepared["store_site"] or task["store"],
                            prepared["listing"] or task["listing"],
                            segment["agent_key"],
                            segment["agent_family"],
                            segment["logic_version"],
                            segment["taxonomy_version"],
                            segment["model_policy_version"],
                            segment["standard_version_id"],
                            segment["claims_version"],
                            now,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO classification_result_versions(
                            id, result_id, source_segment_id, version_no,
                            content_hash, quality_status, publish_status,
                            unit_count, record_count, parent_version_id,
                            version_reason, created_by, created_at, published_at
                        ) VALUES (?, ?, ?, 1, ?, ?, 'publishing', ?, ?, NULL,
                                  '首次发布', ?, ?, NULL)
                        """,
                        (
                            version_id,
                            result_id,
                            segment_id,
                            content_hash,
                            quality_status,
                            len(prepared["units"]),
                            len(prepared["records"]),
                            task["owner_id"],
                            now,
                        ),
                    )
                    self._insert_units(
                        connection,
                        version_id,
                        prepared["units"],
                        prepared["labels"],
                    )
                    self._insert_records(
                        connection,
                        version_id,
                        str(task["dataset_version_id"]),
                        prepared["records"],
                    )
                    connection.execute(
                        """
                        UPDATE classification_result_versions
                        SET publish_status = 'published', published_at = ?
                        WHERE id = ?
                        """,
                        (now, version_id),
                    )
                    connection.execute(
                        """
                        UPDATE task_segments
                        SET status = ?, progress_current = ?, progress_total = ?,
                            model_calls = ?, cache_hits = ?, model_failures = ?,
                            error = NULL,
                            requested_action = NULL, result_json_path = ?,
                            result_version = ?, result_version_id = ?,
                            result_publish_status = 'published',
                            result_quality_status = ?, result_published_at = ?,
                            result_publish_error = NULL, completed_at = ?,
                            heartbeat_at = ?, revision = revision + 1
                        WHERE id = ? AND task_id = ?
                        """,
                        (
                            segment_status,
                            progress_total,
                            progress_total,
                            model_calls,
                            cache_hits,
                            model_failures,
                            checkpoint_path,
                            legacy_result_version,
                            version_id,
                            quality_status,
                            now,
                            now,
                            now,
                            segment_id,
                            task_id,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO task_events(
                            task_id, event_type, stage, message,
                            data_json, created_at
                        ) VALUES (?, 'segment_completed', '语义分析',
                                  'Listing 分类结果已发布', ?, ?)
                        """,
                        (
                            task_id,
                            json_text(
                                {
                                    "segment_id": segment_id,
                                    "status": segment_status,
                                    "result_version_id": version_id,
                                    "result_version": 1,
                                    "quality_status": quality_status,
                                }
                            ),
                            now,
                        ),
                    )
            if conflict is not None:
                raise ResultPublicationConflict(conflict)
        except ResultPublicationConflict:
            raise
        except Exception as exc:
            self.mark_publish_failed(task_id, segment_id, str(exc))
            raise ResultPublicationError(str(exc)) from exc
        version_id = self._published_version_id(segment_id)
        return self.get(version_id)

    def mark_publish_failed(
        self,
        task_id: str,
        segment_id: str,
        error: str,
    ) -> None:
        message = error[:500]
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE task_segments
                SET result_publish_status = 'failed',
                    result_publish_error = ?, revision = revision + 1
                WHERE id = ? AND task_id = ? AND result_version_id IS NULL
                """,
                (message, segment_id, task_id),
            )
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, data_json, created_at
                ) VALUES (?, 'result_publish_failed', '生成结果',
                          'Listing 分类结果发布失败', ?, ?)
                """,
                (
                    task_id,
                    json_text({"segment_id": segment_id, "error": message}),
                    now,
                ),
            )

    def attach_legacy_file(
        self,
        segment_id: str,
        output_path: str,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE task_segments SET result_file_path = ?
                WHERE id = ? AND result_publish_status = 'published'
                """,
                (output_path, segment_id),
            )

    def record_legacy_export_error(
        self,
        task_id: str,
        segment_id: str,
        error: str,
    ) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, data_json, created_at
                ) VALUES (?, 'legacy_export_failed', '生成结果',
                          '兼容 Excel 生成失败，数据库结果仍可查看和下载', ?, ?)
                """,
                (
                    task_id,
                    json_text({"segment_id": segment_id, "error": error[:500]}),
                    now,
                ),
            )

    def list(
        self,
        *,
        page: int = 1,
        page_size: int = PAGE_SIZE_DEFAULT,
        q: str | None = None,
        store_site: str | None = None,
        listing: str | None = None,
        quality_status: str | None = None,
    ) -> dict[str, Any]:
        page, page_size = self._validate_page(page, page_size)
        where = [
            "v.publish_status = 'published'",
            """
            v.version_no = (
                SELECT MAX(latest.version_no)
                FROM classification_result_versions latest
                WHERE latest.result_id = v.result_id
                  AND latest.publish_status = 'published'
            )
            """,
        ]
        params: list[Any] = []
        clean_query = (q or "").strip()
        if clean_query:
            pattern = self._contains_pattern(clean_query)
            where.append(
                """
                EXISTS (
                    SELECT 1 FROM classification_result_records search_record
                    WHERE search_record.result_version_id = v.id
                      AND (
                          search_record.product_name LIKE ? ESCAPE '\\'
                          OR search_record.listing LIKE ? ESCAPE '\\'
                          OR search_record.source_sku LIKE ? ESCAPE '\\'
                          OR search_record.product_sku LIKE ? ESCAPE '\\'
                      )
                )
                """
            )
            params.extend([pattern, pattern, pattern, pattern])
        if store_site:
            where.append("r.store_site = ?")
            params.append(store_site)
        if listing:
            where.append("r.listing = ?")
            params.append(listing)
        if quality_status:
            self._validate_quality_status(quality_status)
            where.append("v.quality_status = ?")
            params.append(quality_status)
        where_sql = " AND ".join(where)
        with self.database.connect() as connection:
            total = int(
                connection.execute(
                    f"""
                    SELECT COUNT(*) FROM classification_result_versions v
                    JOIN classification_results r ON r.id = v.result_id
                    WHERE {where_sql}
                    """,
                    tuple(params),
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                {self._version_select()}
                WHERE {where_sql}
                ORDER BY v.published_at DESC, v.id ASC
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "items": [self._serialize_version(dict(row)) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get(self, version_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            return self._get_version_with_connection(connection, version_id)

    def taxonomy(self, version_id: str) -> TaxonomyConfig | None:
        with self.database.connect() as connection:
            return result_taxonomy(connection, version_id)

    def history(self, version_id: str) -> list[dict[str, Any]]:
        current = self.get(version_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                {self._version_select()}
                WHERE v.result_id = ? AND v.publish_status = 'published'
                ORDER BY v.version_no DESC
                """,
                (current["result_id"],),
            ).fetchall()
        return [self._serialize_version(dict(row)) for row in rows]

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

    def download(self, version_id: str) -> tuple[bytes, str]:
        version = self.get(version_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                {self._records_select()}
                WHERE r.result_version_id = ?
                ORDER BY r.source_row ASC, r.id ASC
                """,
                (version_id,),
            ).fetchall()
        output = []
        semantics = []
        taxonomy = self.taxonomy(version_id)
        for row in rows:
            item = self._enrich_record(self._serialize_record(dict(row)), taxonomy)
            for unit in item["atomic_facts"]:
                path = unit.get("label_path", [])
                semantics.append(
                    {
                        "source_record_id": item["source_record_id"],
                        "source_row": item["source_row"],
                        "label_code": unit["label_code"],
                        "完整路径": " → ".join(path),
                        "中文事实": unit.get("fact_text_zh") or "",
                        "原文证据": unit.get("original_evidence") or "",
                        "事实编号": unit.get("fact_id") or "",
                        "使用者": unit.get("actor_ref") or "",
                        "商品": unit.get("product_ref") or "",
                        "事件": unit.get("event_ref") or "",
                        "陈述类型": unit.get("statement_type") or "",
                        "操作": unit.get("operation") or "",
                        "条件": unit.get("condition") or "",
                        "确定性": unit.get("certainty") or "AFFIRMED",
                        "因果归属": unit.get("causal_attribution") or "UNKNOWN",
                        "因果说明": unit.get("causal_attribution_reason") or "",
                        "判定理由": unit.get("decision_reason") or "",
                        "证据来源": unit.get("evidence_source") or "UNKNOWN",
                        **{
                            f"第{index}级标签": name
                            for index, name in enumerate(path, 1)
                        },
                        "证据原文": unit.get("evidence", ""),
                        "标准版本": version.get("standard_version_id", ""),
                    }
                )
            output.append(
                {
                    "source_record_id": item["source_record_id"],
                    "source_row": item["source_row"],
                    "return_date": item["return_date"],
                    "order_id": item["order_id"],
                    "store_site": item["store_site"],
                    "listing": item["listing"],
                    "product_name": item["product_name"],
                    "source_sku": item["source_sku"],
                    "matched_msku": item["matched_msku"],
                    "product_sku": item["product_sku"],
                    "asin": item["asin"],
                    "category_a": item["category_a"],
                    "category_b": item["category_b"],
                    "reason": item["reason"],
                    "comment": item["comment"],
                    "product_match_status": item["product_match_status"],
                    "quality_status": item["quality_status"],
                    "processing_status": item["processing_status"],
                    "semantic_disposition": item["semantic_disposition"],
                    "problem_labels": " | ".join(item["problem_labels"]),
                    "classification_json": json.dumps(
                        item["classification"],
                        ensure_ascii=False,
                    ),
                }
            )
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            pd.DataFrame(output).to_excel(
                writer,
                sheet_name="分类结果",
                index=False,
            )
            pd.DataFrame(semantics).to_excel(writer, sheet_name="语义层级", index=False)
        filename = (
            f"classification-{version['listing'] or version['result_id']}"
            f"-v{version['version']}.xlsx"
        )
        return buffer.getvalue(), filename

    def _prepare_publication(
        self,
        dataset: ReturnDataset,
        results: dict[str, ValidatedClassification],
        taxonomy: TaxonomyConfig,
    ) -> dict[str, Any]:
        label_map = {label.code: label for label in taxonomy.labels}
        comments = dataset.unique_comments.set_index("classification_key")
        units: list[dict[str, Any]] = []
        labels: list[dict[str, Any]] = []
        quality_by_key: dict[str, str] = {}
        for key in sorted(results):
            result = results[key]
            source = comments.loc[key]
            processing_status = result.status.value
            classification = _prepare_classification_payload(
                result.model_dump(mode="json"),
                taxonomy,
                processing_status,
                include_api_fields=False,
            )
            quality_status = _classification_quality(
                result,
                str(classification["semantic_disposition"]),
            )
            classification.pop("semantic_disposition", None)
            for semantic_unit in classification.get("semantic_units", []):
                semantic_unit.pop("label_code_path", None)
                semantic_unit.pop("label_path", None)
            quality_by_key[key] = quality_status
            units.append(
                {
                    "classification_key": key,
                    "reason": _nullable_text(source.get("reason")),
                    "comment": _nullable_text(source.get("comment_normalized")),
                    "classification": classification,
                    "problem_labels": list(result.problem_label_codes),
                    "processing_status": processing_status,
                    "quality_status": quality_status,
                    "record_count": int(source.get("record_count", 0)),
                    "model_name": result.model_name,
                    "prompt_version": result.prompt_version,
                    "taxonomy_version": result.taxonomy_version,
                }
            )
            for kind, codes in (
                ("problem", result.problem_label_codes),
                ("positive", result.positive_label_codes),
                ("primary", result.primary_label_codes),
            ):
                for code in sorted(set(codes)):
                    label = label_map.get(code)
                    labels.append(
                        {
                            "classification_key": key,
                            "label_kind": kind,
                            "label_code": code,
                            "label_name": label.name if label else None,
                            "label_group": label.group if label else None,
                        }
                    )

        selected = dataset.records.loc[
            dataset.records["classification_key"].isin(results)
        ].copy()
        records: list[dict[str, Any]] = []
        for row in selected.sort_values("source_row").to_dict(orient="records"):
            classification_key = str(row["classification_key"])
            records.append(
                {
                    "classification_key": classification_key,
                    "source_row": int(row["source_row"]),
                    "return_date": _nullable_text(row.get("return-date")),
                    "order_id": _nullable_text(row.get("order-id")),
                    "store_site": _nullable_text(row.get("store")),
                    "listing": _nullable_text(row.get("listing")),
                    "product_name": _nullable_text(row.get("product_name")),
                    "source_sku": _nullable_text(row.get("source_sku")),
                    "matched_msku": _nullable_text(row.get("matched_msku")),
                    "product_sku": _nullable_text(row.get("product_sku")),
                    "asin": _nullable_text(row.get("asin")),
                    "fnsku": _nullable_text(row.get("fnsku")),
                    "category_a": _nullable_text(row.get("category_a")),
                    "category_b": _nullable_text(row.get("category_b")),
                    "reason": _nullable_text(row.get("reason")),
                    "comment": _nullable_text(row.get("comment_raw")),
                    "product_match_status": str(
                        row.get("product_match_status") or "unmatched"
                    ),
                    "quality_status": quality_by_key[classification_key],
                }
            )
        scopes = {(value["store_site"], value["listing"]) for value in records}
        store_site, listing = next(iter(scopes)) if len(scopes) == 1 else (None, None)
        return {
            "units": units,
            "labels": labels,
            "records": records,
            "store_site": store_site,
            "listing": listing,
        }

    @staticmethod
    def _content_hash(
        dataset_version_id: str,
        product_version_id: str,
        units: list[dict[str, Any]],
        records: list[dict[str, Any]],
    ) -> str:
        hasher = hashlib.sha256()
        hasher.update(f"{dataset_version_id}\x1f{product_version_id}\n".encode("utf-8"))
        for values in (units, records):
            for value in values:
                canonical = json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                hasher.update(canonical.encode("utf-8"))
                hasher.update(b"\n")
        return hasher.hexdigest()

    @staticmethod
    def _insert_units(
        connection: Any,
        version_id: str,
        units: list[dict[str, Any]],
        labels: list[dict[str, Any]],
    ) -> None:
        connection.executemany(
            """
            INSERT INTO classification_units(
                id, result_version_id, classification_key, reason, comment,
                classification_json, problem_labels_json,
                processing_status, quality_status, record_count,
                model_name, prompt_version, taxonomy_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    new_id("classification_unit"),
                    version_id,
                    value["classification_key"],
                    value["reason"],
                    value["comment"],
                    json_text(value["classification"]),
                    json_text(value["problem_labels"]),
                    value["processing_status"],
                    value["quality_status"],
                    value["record_count"],
                    value["model_name"],
                    value["prompt_version"],
                    value["taxonomy_version"],
                )
                for value in units
            ],
        )
        connection.executemany(
            """
            INSERT INTO classification_unit_labels(
                result_version_id, classification_key, label_kind,
                label_code, label_name, label_group
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    version_id,
                    value["classification_key"],
                    value["label_kind"],
                    value["label_code"],
                    value["label_name"],
                    value["label_group"],
                )
                for value in labels
            ],
        )

    @staticmethod
    def _insert_records(
        connection: Any,
        version_id: str,
        dataset_version_id: str,
        records: list[dict[str, Any]],
    ) -> None:
        connection.executemany(
            """
            INSERT INTO classification_result_records(
                id, result_version_id, classification_key,
                source_record_id, source_row, return_date, order_id,
                store_site, listing, product_name, source_sku,
                matched_msku, product_sku, asin, fnsku, category_a,
                category_b, reason, comment, product_match_status,
                quality_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?)
            """,
            [
                (
                    new_id("classification_record"),
                    version_id,
                    value["classification_key"],
                    f"{dataset_version_id}:{value['source_row']}",
                    value["source_row"],
                    value["return_date"],
                    value["order_id"],
                    value["store_site"],
                    value["listing"],
                    value["product_name"],
                    value["source_sku"],
                    value["matched_msku"],
                    value["product_sku"],
                    value["asin"],
                    value["fnsku"],
                    value["category_a"],
                    value["category_b"],
                    value["reason"],
                    value["comment"],
                    value["product_match_status"],
                    value["quality_status"],
                )
                for value in records
            ],
        )

    def _published_version_id(self, segment_id: str) -> str:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id FROM classification_result_versions
                WHERE source_segment_id = ? AND version_no = 1
                      AND publish_status = 'published'
                """,
                (segment_id,),
            ).fetchone()
        if row is None:
            raise ResultPublicationError("结果发布事务没有生成可用版本")
        return str(row["id"])

    @staticmethod
    def _version_select() -> str:
        return """
            SELECT v.id AS version_id, v.result_id, v.version_no AS version,
                   v.content_hash, v.quality_status, v.publish_status,
                   v.unit_count, v.record_count, v.created_at,
                   v.published_at, v.parent_version_id, v.version_reason,
                   v.created_by, creator.display_name AS created_by_name,
                   (
                       SELECT batch.id FROM review_batches batch
                       WHERE batch.published_version_id = v.id
                       ORDER BY batch.published_at DESC, batch.id DESC
                       LIMIT 1
                   ) AS source_review_batch_id,
                   (
                       SELECT parent.version_no
                       FROM classification_result_versions parent
                       WHERE parent.id = v.parent_version_id
                   ) AS parent_version_no,
                   COALESCE((
                       SELECT COUNT(DISTINCT revision.review_record_id)
                       FROM review_batches batch
                       JOIN review_records review
                         ON review.batch_id = batch.id
                       JOIN review_revisions revision
                         ON revision.review_record_id = review.id
                       WHERE batch.published_version_id = v.id
                         AND (
                             json_extract(
                                 revision.before_json, '$.semantic_units'
                             ) IS NOT json_extract(
                                 revision.after_json, '$.semantic_units'
                             )
                             OR json_extract(
                                 revision.before_json, '$.unknown_semantics'
                             ) IS NOT json_extract(
                                 revision.after_json, '$.unknown_semantics'
                             )
                             OR json_extract(
                                 revision.before_json, '$.problem_label_codes'
                             ) IS NOT json_extract(
                                 revision.after_json, '$.problem_label_codes'
                             )
                             OR json_extract(
                                 revision.before_json, '$.positive_label_codes'
                             ) IS NOT json_extract(
                                 revision.after_json, '$.positive_label_codes'
                             )
                             OR json_extract(
                                 revision.before_json, '$.primary_label_codes'
                             ) IS NOT json_extract(
                                 revision.after_json, '$.primary_label_codes'
                             )
                         )
                   ), 0) AS changed_unit_count,
                   r.source_task_id, r.source_segment_id,
                   r.dataset_version_id, r.product_version_id,
                   r.store_site, r.listing, r.agent_key, r.agent_family,
                   r.logic_version, r.taxonomy_version,
                   r.model_policy_version, r.standard_version_id,
                   standard.id AS standard_id,
                   standard.name AS standard_name,
                   standard_version.version_no AS standard_version,
                   r.claims_version,
                   rd.name AS dataset_name, dv.version AS dataset_version,
                   pd.name AS product_dataset_name,
                   pv.version AS product_version,
                   COALESCE((
                       SELECT json_group_array(product_name)
                       FROM (
                           SELECT DISTINCT records.product_name AS product_name
                           FROM classification_result_records records
                           WHERE records.result_version_id = v.id
                             AND records.product_name IS NOT NULL
                             AND TRIM(records.product_name) != ''
                           ORDER BY records.product_name COLLATE NOCASE,
                                    records.product_name
                       )
                   ), '[]') AS product_names_json
            FROM classification_result_versions v
            JOIN classification_results r ON r.id = v.result_id
            JOIN dataset_versions dv ON dv.id = r.dataset_version_id
            JOIN datasets rd ON rd.id = dv.dataset_id
            JOIN dataset_versions pv ON pv.id = r.product_version_id
            JOIN datasets pd ON pd.id = pv.dataset_id
            LEFT JOIN classification_standard_versions standard_version
              ON standard_version.id = r.standard_version_id
            LEFT JOIN classification_standards standard
              ON standard.id = standard_version.standard_id
            LEFT JOIN users creator ON creator.id = v.created_by
        """

    def _get_version_with_connection(
        self,
        connection: Any,
        version_id: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            f"{self._version_select()} WHERE v.id = ?",
            (version_id,),
        ).fetchone()
        if row is None:
            raise ClassificationResultNotFound("分类结果版本不存在")
        return self._serialize_version(dict(row))

    @staticmethod
    def _serialize_version(value: dict[str, Any]) -> dict[str, Any]:
        value["product_names"] = json_value(
            value.pop("product_names_json", None),
            [],
        )
        value["changed_unit_count"] = int(value.get("changed_unit_count") or 0)
        value["inherited_unit_count"] = (
            max(int(value.get("unit_count") or 0) - value["changed_unit_count"], 0)
            if value.get("parent_version_id")
            else 0
        )
        value.update(
            result_delivery_state(
                quality_status=value.get("quality_status"),
                publish_status=value.get("publish_status"),
                parent_version_id=value.get("parent_version_id"),
                source_review_batch_id=value.get("source_review_batch_id"),
            )
        )
        return value

    @staticmethod
    def _contains_pattern(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("%", "\\%")
        escaped = escaped.replace("_", "\\_")
        return f"%{escaped}%"

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
