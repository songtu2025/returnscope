"""反馈组人工修正：一次事务发布并更新任务及看板，不创建复核批次。"""

from __future__ import annotations

import hashlib
from typing import Any

from web_backend.classification_result_publication import (
    ResultPublicationConflict,
    SegmentPublicationState,
)
from web_backend.classification_results.effective_content import (
    business_hash,
    load_content,
)
from web_backend.classification_results.publication_transaction import (
    new_publication_version,
)
from web_backend.classification_results.publication_writes import insert_version
from web_backend.common import insert_audit, json_text
from web_backend.dashboards.live_sources import refresh_related_dashboards
from web_backend.result_hierarchy import feedback_group_key_sql, result_taxonomy
from web_backend.review_batches.semantic_validation import _ReviewSemanticValidation
from web_backend.review_label_corrections import apply_semantic_review_changes
from web_backend.reviews.publication_content import ReviewPublicationContentMixin
from web_backend.security import utc_now


def correct_group(
    service: Any,
    version_id: str,
    record_id: str,
    items: list[dict[str, Any]],
    actor_id: str,
) -> dict[str, Any]:
    now = utc_now()
    with service.database.transaction(immediate=True) as connection:
        base = service._get_version_with_connection(connection, version_id)
        latest = connection.execute(
            "SELECT id FROM classification_result_versions WHERE result_id = ? AND publish_status = 'published' ORDER BY version_no DESC LIMIT 1",
            (base["result_id"],),
        ).fetchone()
        if latest["id"] != version_id:
            raise ResultPublicationConflict(
                "结果已更新，请刷新后重新修正；当前输入已保留"
            )
        segment = connection.execute(
            "SELECT * FROM task_segments WHERE id = ?", (base["source_segment_id"],)
        ).fetchone()
        if segment["status"] in {
            "running",
            "queued",
            "retry_pending",
            "pause_requested",
        }:
            raise ResultPublicationConflict(
                "Listing 正在执行，请结束后保存；当前输入已保留"
            )
        members = _group_members(connection, version_id, record_id)
        content = load_content(connection, version_id)
        before = business_hash(content)
        original = next(
            unit
            for unit in content["units"]
            if unit["classification_key"] == members[0]["classification_key"]
        )
        taxonomy = result_taxonomy(connection, version_id)
        if taxonomy is None:
            raise ValueError("当前结果缺少分类标准，无法校验人工修正")
        validation = _ReviewSemanticValidation()
        validation._validate_added_semantic_items(
            items,
            str(members[0]["comment"] or ""),
            {label.code for label in taxonomy.labels},
        )
        classification = _manual_classification(
            original["classification"], items, taxonomy, actor_id, now
        )
        old_key = original["classification_key"]
        source_rows = sorted(member["source_row"] for member in members)
        key = (
            "manual:" + hashlib.sha256(json_text(source_rows).encode()).hexdigest()[:24]
        )
        classification["classification_key"] = key
        classification["human_review_assessment"]["original_classification_key"] = (
            original["classification"]
            .get("human_review_assessment", {})
            .get("original_classification_key", old_key)
        )
        _replace_group(content, original, classification, set(source_rows), taxonomy)
        if before == business_hash(content):
            return base
        version = new_publication_version(
            connection,
            {"result_id": base["result_id"], "id": version_id},
            content,
            business_hash(content),
            now,
        )
        task = connection.execute(
            "SELECT * FROM tasks WHERE id = ?", (base["source_task_id"],)
        ).fetchone()
        state = SegmentPublicationState(
            task_id=task["id"],
            segment_id=segment["id"],
            segment_status=segment["status"],
            progress_total=segment["progress_total"],
            model_calls=segment["model_calls"],
            cache_hits=segment["cache_hits"],
            checkpoint_path=segment["result_json_path"] or "",
            legacy_result_version=segment["result_version"] or 0,
        )
        insert_version(connection, task, state, content, version)
        service._insert_units(
            connection, version.version_id, content["units"], content["labels"]
        )
        service._insert_records(
            connection,
            version.version_id,
            base["dataset_version_id"],
            content["records"],
        )
        connection.execute(
            "UPDATE classification_result_versions SET publish_status = 'published', published_at = ?, created_by = ?, version_reason = '反馈组人工修正' WHERE id = ?",
            (now, actor_id, version.version_id),
        )
        connection.execute(
            "UPDATE task_segments SET result_version_id = ?, result_quality_status = ?, result_published_at = ?, revision = revision + 1 WHERE id = ?",
            (version.version_id, version.quality_status, now, segment["id"]),
        )
        insert_audit(
            connection,
            "classification_result",
            base["result_id"],
            "manual_correction",
            actor_id,
            {"version_id": version_id, "classification": original["classification"]},
            {
                "version_id": version.version_id,
                "source_rows": source_rows,
                "classification": classification,
                "reason": "人工修正语义",
            },
            now,
        )
        refresh_related_dashboards(service.database, connection, base["result_id"], now)
        return service._get_version_with_connection(connection, version.version_id)


def _group_members(connection: Any, version_id: str, record_id: str) -> list[Any]:
    identity = feedback_group_key_sql("r")
    rows = connection.execute(
        f"""WITH records AS (SELECT r.*, {identity} AS group_key FROM classification_result_records r WHERE result_version_id = ?)
        SELECT * FROM records WHERE group_key = (SELECT group_key FROM records WHERE id = ?) ORDER BY source_row""",
        (version_id, record_id),
    ).fetchall()
    if not rows:
        raise ValueError("当前反馈记录不存在")
    return rows


def _manual_classification(
    original: dict[str, Any],
    items: list[dict[str, Any]],
    taxonomy: Any,
    actor_id: str,
    now: str,
) -> dict[str, Any]:
    # 修改既有观点时保留部位、对象等已提取信息，人工只替换可编辑字段。
    enriched = []
    for item in items:
        item_id = str(item.get("item_id") or "")
        source = {}
        if item_id.startswith("unit:"):
            try:
                source = original["semantic_units"][int(item_id.removeprefix("unit:"))]
            except (ValueError, IndexError):
                raise ValueError("待修改的语义观点已不存在") from None
        preserved = {
            key: value
            for key, value in source.items()
            if key not in {"evidence", "sentiment", "label_code", "opinion"}
        }
        enriched.append(
            {**preserved, **item, "assessed_by": actor_id, "assessed_at": now}
        )
    core = {
        **original,
        "semantic_units": [],
        "unknown_semantics": [],
        "extracted_facts": [],
        "fact_mappings": [],
        "dimension_decisions": [],
        "semantic_relations": [],
        "comment_summary": {},
        "review_diagnostics": [],
        "review_reasons": [],
        "primary_label_codes": [],
        "problem_label_codes": [],
        "positive_label_codes": [],
        "human_semantic_reviews": [],
        "human_added_semantic_items": enriched,
        "status": "MANUAL_RESOLVED",
        "human_review_assessment": {
            "resolved": True,
            "assessed_by": actor_id,
            "assessed_at": now,
        },
    }
    core.pop("semantic_review", None)
    result = apply_semantic_review_changes(core, taxonomy)
    validated, human = ReviewPublicationContentMixin._validate_reviewed_classification(
        result
    )
    return {**validated.model_dump(mode="json"), **human}


def _replace_group(
    content: dict[str, Any],
    original: dict[str, Any],
    classification: dict[str, Any],
    source_rows: set[int],
    taxonomy: Any,
) -> None:
    key = classification["classification_key"]
    for record in content["records"]:
        if record["source_row"] in source_rows:
            record.update(classification_key=key, quality_status="ready")
    remaining = sum(
        record["classification_key"] == original["classification_key"]
        for record in content["records"]
    )
    original["record_count"] = remaining
    content["units"] = [
        unit
        for unit in content["units"]
        if unit["record_count"] and unit["classification_key"] != key
    ]
    content["units"].append(
        {
            **original,
            "classification_key": key,
            "classification": classification,
            "record_count": len(source_rows),
            "problem_labels": classification["problem_label_codes"],
            "processing_status": "MANUAL_RESOLVED",
            "quality_status": "ready",
        }
    )
    content["labels"] = [
        label
        for label in content["labels"]
        if label["classification_key"] != key
        and (remaining or label["classification_key"] != original["classification_key"])
    ]
    validated, _human = ReviewPublicationContentMixin._validate_reviewed_classification(
        classification
    )
    content["labels"].extend(
        ReviewPublicationContentMixin._derive_unit_labels(
            key, validated, {label.code: label for label in taxonomy.labels}
        )
    )
