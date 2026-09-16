from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import get_type_hints

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from test_classification_result_pool import _publish, _seed_result_context

from return_semantics.schemas import ProcessingStatus
from web_backend import review_service as review_service_module
from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.common import json_text
from web_backend.dashboard_service import DashboardService
from web_backend.review_service import (
    ReviewBatchConflict,
    ReviewService,
    RevisionConflict,
)
from web_backend.routers.accounts import create_account_router
from web_backend.routers.classification_results import (
    create_classification_result_router,
)
from web_backend.routers.reviews import create_review_router
from web_backend.task_service import TaskService


def _publish_review_required(tmp_path: Path):
    context = _seed_result_context(tmp_path)
    source = context.results[context.key]
    context.results = {
        context.key: source.model_copy(
            update={
                "status": ProcessingStatus.MANUAL_REVIEW,
                "review_reasons": ["需要人工确认"],
            }
        )
    }
    version = _publish(context)
    standards = ClassificationStandardService(context.database)
    standard = next(
        item for item in standards.list() if item["standard_key"] == "footwear"
    )
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE classification_results SET standard_version_id = ? WHERE id = ?",
            (standard["standard_version_id"], version["result_id"]),
        )
        connection.execute(
            """
            INSERT INTO users(id, email, display_name, password_hash, created_at)
            VALUES ('user-2', 'two@example.com', '用户二', 'hash', ?)
            """,
            ("2026-08-12T00:03:00+00:00",),
        )
    return context, version


def test_review_service_preserves_public_method_contract() -> None:
    expected_signatures = {
        "list": "(self, workflow_status: str | None = None, task_id: str | None = None) -> list[dict[str, typing.Any]]",
        "get": "(self, review_id: str) -> dict[str, typing.Any] | None",
        "create_batch": "(self, base_result_version_id: str, actor_id: str, reason: str) -> dict[str, typing.Any]",
        "list_batches": "(self, *, page: int = 1, page_size: int = 50, status: str | None = None, base_result_version_id: str | None = None, q: str | None = None) -> dict[str, typing.Any]",
        "get_batch": "(self, batch_id: str) -> dict[str, typing.Any]",
        "batch_records": "(self, batch_id: str, *, page: int = 1, page_size: int = 50, workflow_status: str | None = None, q: str | None = None, listing: str | None = None, product_name: str | None = None, product_sku: str | None = None, order_id: str | None = None) -> dict[str, typing.Any]",
        "update_batch_record": "(self, batch_id: str, review_id: str, expected_revision: int, actor_id: str, label_code: str | None, note: str, action: str | None = None, review_assessment: dict[str, str | None] | None = None) -> dict[str, typing.Any]",
        "update_batch_records": "(self, batch_id: str, records: list[dict[str, typing.Any]], actor_id: str, action: str, label_code: str | None, note: str, review_assessment: dict[str, str | None] | None = None) -> dict[str, typing.Any]",
        "publish_batch": "(self, batch_id: str, expected_revision: int, actor_id: str, reason: str) -> dict[str, typing.Any]",
        "resolve": "(self, review_id: str, expected_revision: int, actor_id: str, label_code: str | None, note: str) -> dict[str, typing.Any]",
    }

    def resolved_signature(name: str) -> str:
        method = getattr(ReviewService, name)
        type_hints = get_type_hints(method)
        signature = inspect.signature(method)
        return str(
            signature.replace(
                parameters=[
                    parameter.replace(
                        annotation=type_hints.get(
                            parameter_name, inspect.Signature.empty
                        )
                    )
                    for parameter_name, parameter in signature.parameters.items()
                ],
                return_annotation=type_hints["return"],
            )
        )

    assert {
        name: resolved_signature(name) for name in expected_signatures
    } == expected_signatures
    assert all(
        inspect.isfunction(inspect.getattr_static(ReviewService, name))
        for name in expected_signatures
    )

    static_entries = {
        "_load_completed_review_changes",
        "_validate_reviewed_classification",
        "_build_derived_result_content",
        "_top_problem_labels",
        "_version_quality",
        "_insert_audit",
        "_serialize_batch",
        "_serialize",
        "_serialize_revision",
    }
    assert all(
        isinstance(inspect.getattr_static(ReviewService, name), staticmethod)
        for name in static_entries
    )
    assert isinstance(
        inspect.getattr_static(ReviewService, "_serialize_batch_record"), classmethod
    )


def test_review_service_preserves_exception_import_contract() -> None:
    assert RevisionConflict is review_service_module.RevisionConflict
    assert ReviewBatchConflict is review_service_module.ReviewBatchConflict
    assert issubclass(RevisionConflict, ValueError)
    assert issubclass(ReviewBatchConflict, ValueError)
    assert RevisionConflict.__module__ == "web_backend.review_service"
    assert ReviewBatchConflict.__module__ == "web_backend.review_service"


def test_review_service_rebuild_result_remains_instance_patchable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = object.__new__(ReviewService)
    calls: list[tuple[str, str]] = []

    def replacement(task_id: str, actor_id: str) -> None:
        calls.append((task_id, actor_id))

    monkeypatch.setattr(service, "_rebuild_result", replacement)

    service._rebuild_result("task-1", "user-1")

    assert calls == [("task-1", "user-1")]


def test_review_router_preserves_registration_contract(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)

    def current_user() -> dict[str, str]:
        return {"id": "user-1"}

    router = create_review_router(
        ReviewService(context.database),
        context.database,
        current_user,
    )
    routes = [route for route in router.routes if isinstance(route, APIRoute)]
    expected_routes = [
        "GET|/api/reviews|list_reviews|200|_user,workflow_status,task_id",
        "GET|/api/reviews/{review_id}|get_review|200|review_id,_user",
        "PATCH|/api/reviews/{review_id}|resolve_review|200|review_id,payload,user",
        "POST|/api/classification-results/{version_id}/review-batches|create_review_batch|201|version_id,payload,user",
        "GET|/api/review-batches|list_review_batches|200|_user,page,page_size,status,base_result_version_id,q",
        "GET|/api/review-batches/{batch_id}|get_review_batch|200|batch_id,_user",
        "GET|/api/review-batches/{batch_id}/records|list_review_batch_records|200|batch_id,_user,page,page_size,workflow_status,q,listing,product_name,product_sku,order_id",
        "PATCH|/api/review-batches/{batch_id}/records/{review_id}|update_review_batch_record|200|batch_id,review_id,payload,user",
        "PATCH|/api/review-batches/{batch_id}/records|update_review_batch_records|200|batch_id,payload,user",
        "POST|/api/review-batches/{batch_id}/publish|publish_review_batch|200|batch_id,payload,user",
        "GET|/api/taxonomy|taxonomy|200|_user",
        "GET|/api/audit/{entity_type}/{entity_id}|audit|200|entity_type,entity_id,_user",
    ]

    actual_routes = [
        "|".join(
            (
                next(iter(route.methods)),
                route.path,
                route.name,
                str(route.status_code or 200),
                ",".join(inspect.signature(route.endpoint).parameters),
            )
        )
        for route in routes
    ]
    assert actual_routes == expected_routes
    assert all(not inspect.iscoroutinefunction(route.endpoint) for route in routes)
    assert all(len(route.dependant.dependencies) == 1 for route in routes)


def test_system_status_excludes_legacy_review_records(tmp_path: Path) -> None:
    context, base = _publish_review_required(tmp_path)
    service = ReviewService(context.database)
    service.create_batch(str(base["version_id"]), "user-1", "创建复核批次")
    with context.database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO review_records(
                id, task_id, classification_key, comment,
                workflow_status, classification_json, revision, updated_at
            ) VALUES (
                'legacy-review-for-status', ?, ?, '旧式重复记录',
                'pending', '{}', 1, '2026-08-12T00:00:00+00:00'
            )
            """,
            (context.task_id, context.key),
        )

    app = FastAPI()
    app.include_router(
        create_account_router(
            database=context.database,
            settings=SimpleNamespace(
                bootstrap_password="secure-password",
                encryption_key="configured",
                task_workers=1,
            ),
            session_service=object(),
            account_login_limiter=object(),
            address_login_limiter=object(),
            dummy_password_hash="unused",
            task_service=TaskService(context.database),
            worker=SimpleNamespace(
                is_alive=True,
                health={"last_error_type": None, "last_error_at": None},
            ),
            insight_report_worker=SimpleNamespace(
                is_alive=True,
                health={"last_error_type": None, "last_error_at": None},
            ),
            standard_validation_worker=SimpleNamespace(
                is_alive=True,
                health={"last_error_type": None, "last_error_at": None},
            ),
            start_worker=False,
            current_user=lambda: {"id": "user-1"},
        )
    )

    payload = TestClient(app).get("/api/system/status").json()
    assert payload["pending_reviews"] == 1
    assert payload["pending_review_batches"] == 1


def test_review_record_keeps_independent_quality_assessment(tmp_path: Path) -> None:
    context, base = _publish_review_required(tmp_path)
    service = ReviewService(context.database)
    batch = service.create_batch(str(base["version_id"]), "user-1", "验证复核口径")
    review = service.batch_records(batch["id"])["items"][0]

    updated = service.update_batch_record(
        batch_id=batch["id"],
        review_id=review["id"],
        expected_revision=review["revision"],
        actor_id="user-1",
        label_code=None,
        note="标签正确，但证据展示不完整且本条无需人工复核",
        action="confirm",
        review_assessment={
            "label_correctness": "correct",
            "evidence_completeness": "partial",
            "review_routing": "should_auto_approve",
        },
    )

    assessment = updated["classification"]["human_review_assessment"]
    assert assessment["label_correctness"] == "correct"
    assert assessment["evidence_completeness"] == "partial"
    assert assessment["review_routing"] == "should_auto_approve"
    assert assessment["assessed_by"] == "user-1"
    assert assessment["assessed_at"]
    assert updated["revisions"][0]["after"]["human_review_assessment"] == assessment

    current_batch = service.get_batch(batch["id"])
    derived = service.publish_batch(
        batch["id"],
        current_batch["revision"],
        "user-1",
        "发布包含人工评估的复核结果",
    )
    published = ClassificationResultService(context.database).records(
        derived["version_id"],
        page_size=200,
    )["items"][0]["classification"]
    assert published["human_review_assessment"] == assessment


def test_review_modify_preserves_other_semantic_units_and_indexes(
    tmp_path: Path,
) -> None:
    context, base = _publish_review_required(tmp_path)
    classification = context.results[context.key].model_dump(mode="json")
    original_unit = dict(classification["semantic_units"][0])
    second_unit = {
        **original_unit,
        "label_code": "FIT_TOO_LONG_U1",
        "opinion": "鞋子长度偏长",
        "evidence": "鞋子太大。",
    }
    classification["semantic_units"] = [original_unit, second_unit]
    classification["problem_label_codes"] = [
        original_unit["label_code"],
        second_unit["label_code"],
    ]
    classification["primary_label_codes"] = [original_unit["label_code"]]
    classification["comment_summary"]["negative_label_codes"] = list(
        classification["problem_label_codes"]
    )
    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE classification_units SET classification_json = ?
            WHERE result_version_id = ? AND classification_key = ?
            """,
            (json_text(classification), base["version_id"], context.key),
        )

    service = ReviewService(context.database)
    batch = service.create_batch(str(base["version_id"]), "user-1", "验证多语义修改")
    review = service.batch_records(batch["id"])["items"][0]
    updated = service.update_batch_record(
        batch["id"],
        review["id"],
        review["revision"],
        "user-1",
        "FIT_TOO_SMALL_U1",
        "只修正主问题语义",
    )["classification"]

    assert [unit["label_code"] for unit in updated["semantic_units"]] == [
        "FIT_TOO_SMALL_U1",
        "FIT_TOO_LONG_U1",
    ]
    assert updated["problem_label_codes"] == [
        "FIT_TOO_SMALL_U1",
        "FIT_TOO_LONG_U1",
    ]
    assert updated["primary_label_codes"] == ["FIT_TOO_SMALL_U1"]
    assert updated["comment_summary"]["negative_label_codes"] == [
        "FIT_TOO_SMALL_U1",
        "FIT_TOO_LONG_U1",
    ]

    current_batch = service.get_batch(batch["id"])
    derived = service.publish_batch(
        batch["id"],
        current_batch["revision"],
        "user-1",
        "发布多语义修正",
    )
    with context.database.connect() as connection:
        problem_codes = {
            row["label_code"]
            for row in connection.execute(
                """
                SELECT label_code FROM classification_unit_labels
                WHERE result_version_id = ? AND label_kind = 'problem'
                """,
                (derived["version_id"],),
            ).fetchall()
        }
    assert problem_codes == {"FIT_TOO_SMALL_U1", "FIT_TOO_LONG_U1"}


def test_publish_batch_rejects_outdated_base_version(tmp_path: Path) -> None:
    context, base = _publish_review_required(tmp_path)
    base_id = str(base["version_id"])
    service = ReviewService(context.database)

    first_batch = service.create_batch(base_id, "user-1", "发布首轮修正")
    first_review = service.batch_records(first_batch["id"])["items"][0]
    service.update_batch_record(
        first_batch["id"],
        first_review["id"],
        first_review["revision"],
        "user-1",
        "FIT_TOO_SMALL_U1",
        "首轮修正",
    )
    service.publish_batch(
        first_batch["id"],
        service.get_batch(first_batch["id"])["revision"],
        "user-1",
        "发布第二版",
    )

    stale_batch = service.create_batch(base_id, "user-2", "从旧版本再次创建复核")
    stale_review = service.batch_records(stale_batch["id"])["items"][0]
    service.update_batch_record(
        stale_batch["id"],
        stale_review["id"],
        stale_review["revision"],
        "user-2",
        "FIT_TOO_LARGE_U1",
        "不应覆盖第二版",
    )

    with pytest.raises(ReviewBatchConflict, match="基准分类结果版本已过期"):
        service.publish_batch(
            stale_batch["id"],
            service.get_batch(stale_batch["id"])["revision"],
            "user-2",
            "尝试发布旧基线",
        )
    with context.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_result_versions"
            ).fetchone()[0]
            == 2
        )


def _replace_with_legacy_review_schema(context: SimpleNamespace) -> None:
    with context.database.connect() as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.executescript(
            """
            DROP INDEX IF EXISTS idx_review_records_batch;
            DROP INDEX IF EXISTS idx_review_records_status;
            DROP TABLE review_revisions;
            DROP TABLE review_records;

            CREATE TABLE review_records (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                classification_key TEXT NOT NULL,
                comment TEXT NOT NULL,
                workflow_status TEXT NOT NULL DEFAULT 'pending',
                classification_json TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 1,
                updated_by TEXT REFERENCES users(id),
                updated_at TEXT NOT NULL,
                UNIQUE(task_id, classification_key)
            );
            CREATE INDEX idx_review_records_status
            ON review_records(workflow_status, updated_at DESC);
            CREATE TABLE review_revisions (
                id TEXT PRIMARY KEY,
                review_record_id TEXT NOT NULL REFERENCES review_records(id),
                revision INTEGER NOT NULL,
                before_json TEXT NOT NULL,
                after_json TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                actor_id TEXT NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL
            );
            """
        )
        classification_json = json_text(
            context.results[context.key].model_dump(mode="json")
        )
        connection.execute(
            """
            INSERT INTO review_records(
                id, task_id, classification_key, comment,
                workflow_status, classification_json,
                revision, updated_by, updated_at
            ) VALUES ('legacy-review', ?, ?, '旧复核记录', 'pending', ?, 1, ?, ?)
            """,
            (
                context.task_id,
                context.key,
                classification_json,
                "user-1",
                "2026-08-12T00:04:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO review_revisions(
                id, review_record_id, revision, before_json, after_json,
                note, actor_id, created_at
            ) VALUES ('legacy-revision', 'legacy-review', 1, ?, ?,
                      '旧复核历史', 'user-1', ?)
            """,
            (
                classification_json,
                classification_json,
                "2026-08-12T00:04:00+00:00",
            ),
        )
        connection.execute("PRAGMA foreign_keys = ON")


def test_review_batch_publishes_immutable_complete_v2_without_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, base = _publish_review_required(tmp_path)
    base_id = str(base["version_id"])
    result_service = ClassificationResultService(context.database)
    review_service = ReviewService(context.database, result_service)
    base_detail = result_service.get(base_id)
    base_records = result_service.records(base_id, page_size=200)
    assert base_detail["source_review_batch_id"] is None
    assert base_detail["parent_version_no"] is None
    assert base_detail["changed_unit_count"] == 0
    assert base_detail["inherited_unit_count"] == 0

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("发布复核版本不得调用模型或旧任务重建")

    monkeypatch.setattr(
        "web_backend.agent_runner.classify_comments",
        forbidden,
    )
    monkeypatch.setattr(review_service, "_rebuild_result", forbidden)

    batch = review_service.create_batch(base_id, "user-1", "创建首轮复核")
    records = review_service.batch_records(batch["id"])
    assert records["total"] == 1
    review = records["items"][0]
    updated = review_service.update_batch_record(
        batch["id"],
        review["id"],
        1,
        "user-1",
        "FIT_TOO_SMALL_U1",
        "确认尺码偏小",
    )
    assert updated["classification"]["status"] == "MANUAL_RESOLVED"
    assert result_service.get(base_id) == base_detail

    with pytest.raises(RevisionConflict):
        review_service.update_batch_record(
            batch["id"],
            review["id"],
            1,
            "user-2",
            "FIT_TOO_SMALL_U1",
            "并发覆盖",
        )

    current_batch = review_service.get_batch(batch["id"])
    derived = review_service.publish_batch(
        batch["id"],
        current_batch["revision"],
        "user-1",
        "发布人工确认结果",
    )
    derived_id = str(derived["version_id"])
    published_batch = review_service.get_batch(batch["id"])

    assert derived["version"] == 2
    assert derived["parent_version_id"] == base_id
    assert derived["version_reason"] == "发布人工确认结果"
    assert derived["created_by"] == "user-1"
    assert derived["created_by_name"] == "用户一"
    assert derived["source_review_batch_id"] == batch["id"]
    assert derived["parent_version_no"] == 1
    assert derived["changed_unit_count"] == 0
    assert derived["inherited_unit_count"] == 1
    assert published_batch["status"] == "published"
    assert published_batch["published_version_id"] == derived_id
    assert published_batch["revision"] == current_batch["revision"] + 1
    assert result_service.get(base_id) == base_detail
    derived_records = result_service.records(derived_id, page_size=200)
    assert derived_records["total"] == base_records["total"] == 3
    for original, revised in zip(
        base_records["items"],
        derived_records["items"],
        strict=True,
    ):
        for field in (
            "source_record_id",
            "order_id",
            "store_site",
            "listing",
            "product_name",
            "source_sku",
            "matched_msku",
            "product_sku",
            "asin",
            "comment",
        ):
            assert revised[field] == original[field]
        assert (
            revised["classification"]["semantic_units"][0]["evidence"]
            == (original["classification"]["semantic_units"][0]["evidence"])
        )
        assert revised["processing_status"] == "MANUAL_RESOLVED"

    listed_version = result_service.list()["items"][0]
    assert listed_version["version_id"] == derived_id
    assert listed_version["created_by_name"] == "用户一"
    assert listed_version["source_review_batch_id"] == batch["id"]
    assert listed_version["changed_unit_count"] == 0
    assert listed_version["inherited_unit_count"] == 1
    history = result_service.history(base_id)
    assert [item["version"] for item in history] == [2, 1]
    assert [item["created_by_name"] for item in history] == ["用户一", "用户一"]
    assert [item["parent_version_no"] for item in history] == [1, None]
    assert [item["changed_unit_count"] for item in history] == [0, 0]
    assert [item["inherited_unit_count"] for item in history] == [1, 0]
    assert result_service.summary(derived_id)["quality"][0]["quality_status"] == (
        "ready"
    )
    assert result_service.drilldown(derived_id, "problem")["total"] == 1
    assert result_service.download(derived_id)[0].startswith(b"PK")

    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE classification_result_versions SET created_by = NULL
            WHERE id = ?
            """,
            (derived_id,),
        )
    assert result_service.get(derived_id)["created_by_name"] is None
    assert result_service.list()["items"][0]["created_by_name"] is None
    missing_creator_history = result_service.history(derived_id)
    assert missing_creator_history[0]["created_by"] is None
    assert missing_creator_history[0]["created_by_name"] is None

    with pytest.raises(ReviewBatchConflict, match="已经发布"):
        review_service.publish_batch(
            batch["id"],
            review_service.get_batch(batch["id"])["revision"],
            "user-2",
            "重复发布",
        )
    with context.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_result_versions"
            ).fetchone()[0]
            == 2
        )
        actions = {
            row["action"]
            for row in connection.execute(
                "SELECT action FROM audit_logs WHERE entity_id = ?",
                (batch["id"],),
            ).fetchall()
        }
    assert {"create", "update_record", "publish", "conflict"}.issubset(actions)


def test_publish_batch_rejects_stale_revision_and_pending_records(
    tmp_path: Path,
) -> None:
    context, base = _publish_review_required(tmp_path)
    review_service = ReviewService(context.database)
    batch = review_service.create_batch(
        str(base["version_id"]),
        "user-1",
        "验证发布阻断",
    )

    with pytest.raises(
        RevisionConflict,
        match="批次已被其他用户修改，请刷新后重试",
    ):
        review_service.publish_batch(
            batch["id"],
            batch["revision"] + 1,
            "user-2",
            "陈旧修订发布",
        )
    with pytest.raises(
        ReviewBatchConflict,
        match="复核批次仍有 1 条记录未完成",
    ):
        review_service.publish_batch(
            batch["id"],
            batch["revision"],
            "user-1",
            "未完成记录发布",
        )

    current_batch = review_service.get_batch(batch["id"])
    assert current_batch["status"] == "draft"
    assert current_batch["revision"] == batch["revision"]
    assert current_batch["published_version_id"] is None
    with context.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_result_versions"
            ).fetchone()[0]
            == 1
        )


def test_publish_batch_rolls_back_failed_derived_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, base = _publish_review_required(tmp_path)
    base_id = str(base["version_id"])
    result_service = ClassificationResultService(context.database)
    review_service = ReviewService(context.database, result_service)
    batch = review_service.create_batch(base_id, "user-1", "验证发布回滚")
    review = review_service.batch_records(batch["id"])["items"][0]
    review_service.update_batch_record(
        batch["id"],
        review["id"],
        review["revision"],
        "user-1",
        "FIT_TOO_SMALL_U1",
        "完成复核后模拟发布失败",
    )
    current_batch = review_service.get_batch(batch["id"])

    def fail_insert_records(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("模拟派生记录写入失败")

    monkeypatch.setattr(result_service, "_insert_records", fail_insert_records)
    with pytest.raises(RuntimeError, match="模拟派生记录写入失败"):
        review_service.publish_batch(
            batch["id"],
            current_batch["revision"],
            "user-1",
            "不应留下半成品",
        )

    rolled_back_batch = review_service.get_batch(batch["id"])
    assert rolled_back_batch["status"] == "draft"
    assert rolled_back_batch["revision"] == current_batch["revision"]
    assert rolled_back_batch["published_version_id"] is None
    assert rolled_back_batch["published_at"] is None
    with context.database.connect() as connection:
        assert (
            connection.execute(
                """
                SELECT COUNT(*) FROM classification_result_versions
                WHERE parent_version_id = ? OR publish_status = 'publishing'
                """,
                (base_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                """
                SELECT COUNT(*) FROM classification_units
                WHERE result_version_id != ?
                """,
                (base_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                """
                SELECT COUNT(*) FROM audit_logs
                WHERE entity_id = ? AND action = 'publish'
                """,
                (batch["id"],),
            ).fetchone()[0]
            == 0
        )


def test_review_batch_api_and_version_history_contract(tmp_path: Path) -> None:
    context, base = _publish_review_required(tmp_path)
    result_service = ClassificationResultService(context.database)
    review_service = ReviewService(context.database, result_service)
    app = FastAPI()

    def current_user() -> dict[str, str]:
        return {"id": "user-1"}

    app.include_router(
        create_review_router(review_service, context.database, current_user)
    )
    app.include_router(
        create_classification_result_router(result_service, current_user)
    )
    client = TestClient(app)

    created = client.post(
        f"/api/classification-results/{base['version_id']}/review-batches",
        json={"reason": "API 创建复核"},
    )
    assert created.status_code == 201
    batch = created.json()
    listed = client.get(f"/api/review-batches/{batch['id']}/records")
    assert listed.status_code == 200
    record = listed.json()["items"][0]
    changed = client.patch(
        f"/api/review-batches/{batch['id']}/records/{record['id']}",
        json={
            "expected_revision": 1,
            "label_code": "FIT_TOO_SMALL_U1",
            "reason": "API 修改",
        },
    )
    assert changed.status_code == 200
    current = client.get(f"/api/review-batches/{batch['id']}").json()
    published = client.post(
        f"/api/review-batches/{batch['id']}/publish",
        json={"expected_revision": current["revision"], "reason": "API 发布"},
    )
    assert published.status_code == 200
    history = client.get(f"/api/classification-results/{base['version_id']}/versions")
    assert history.status_code == 200
    assert [item["version"] for item in history.json()] == [2, 1]


def test_bulk_exclusion_is_auditable_and_does_not_block_publication(
    tmp_path: Path,
) -> None:
    context, base = _publish_review_required(tmp_path)
    result_service = ClassificationResultService(context.database)
    review_service = ReviewService(context.database, result_service)
    app = FastAPI()

    def current_user() -> dict[str, str]:
        return {"id": "user-1"}

    app.include_router(
        create_review_router(review_service, context.database, current_user)
    )
    client = TestClient(app)
    batch = client.post(
        f"/api/classification-results/{base['version_id']}/review-batches",
        json={"reason": "验证批量排除"},
    ).json()
    record = client.get(f"/api/review-batches/{batch['id']}/records").json()["items"][0]

    updated = client.patch(
        f"/api/review-batches/{batch['id']}/records",
        json={
            "records": [
                {
                    "id": record["id"],
                    "expected_revision": record["revision"],
                }
            ],
            "action": "exclude",
            "reason": "该评论不纳入语义分析和看板",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["updated_count"] == 1
    current_batch = updated.json()["batch"]
    assert current_batch["excluded_count"] == 1
    assert current_batch["resolved_count"] == 0
    assert current_batch["remaining_count"] == 0
    excluded = client.get(f"/api/review-batches/{batch['id']}/records").json()["items"][
        0
    ]
    assert excluded["workflow_status"] == "excluded"
    assert excluded["classification"] == record["classification"]

    published = client.post(
        f"/api/review-batches/{batch['id']}/publish",
        json={
            "expected_revision": current_batch["revision"],
            "reason": "发布包含排除记录的复核版本",
        },
    )
    assert published.status_code == 200
    derived = published.json()
    assert derived["quality_status"] == "ready"
    derived_records = result_service.records(
        derived["version_id"],
        page_size=200,
    )
    assert derived_records["total"] == 3
    assert {item["quality_status"] for item in derived_records["items"]} == {"excluded"}
    assert result_service.drilldown(derived["version_id"], "problem")["total"] == 0

    plan = DashboardService(context.database).preflight(
        [derived["version_id"]],
        {},
    )
    assert plan["ready"] is True
    assert plan["filters"] == {"quality_status": ["ready"]}
    assert plan["summary"]["record_count"] == 0
    assert plan["summary"]["total_record_count"] == 3
    assert plan["summary"]["excluded_record_count"] == 3


def test_empty_legacy_batch_cannot_publish(tmp_path: Path) -> None:
    context, base = _publish_review_required(tmp_path)
    review_service = ReviewService(context.database)
    batch = review_service.create_batch(
        str(base["version_id"]),
        "user-1",
        "模拟历史空批次",
    )
    with context.database.transaction() as connection:
        connection.execute(
            "DELETE FROM review_records WHERE batch_id = ?",
            (batch["id"],),
        )

    empty_batch = review_service.get_batch(batch["id"])
    assert empty_batch["record_count"] == 0
    with pytest.raises(ReviewBatchConflict, match="没有可处理"):
        review_service.publish_batch(
            batch["id"],
            empty_batch["revision"],
            "user-1",
            "不应发布",
        )


def test_initialize_repairs_empty_draft_review_batch(tmp_path: Path) -> None:
    context, base = _publish_review_required(tmp_path)
    review_service = ReviewService(context.database)
    batch = review_service.create_batch(
        str(base["version_id"]),
        "user-1",
        "模拟旧版空批次",
    )
    with context.database.transaction() as connection:
        connection.execute(
            "DELETE FROM review_records WHERE batch_id = ?",
            (batch["id"],),
        )
        connection.execute(
            """
            INSERT INTO review_records(
                id, task_id, classification_key, comment,
                workflow_status, classification_json, updated_at
            ) VALUES ('legacy-review', ?, ?, '旧版复核记录', 'pending', ?, ?)
            """,
            (
                context.task_id,
                context.key,
                json_text(context.results[context.key].model_dump(mode="json")),
                "2026-08-12T00:04:00+00:00",
            ),
        )

    context.database.initialize()
    context.database.initialize()

    repaired = review_service.get_batch(batch["id"])
    assert repaired["record_count"] == 1
    assert repaired["remaining_count"] == 1
    with context.database.connect() as connection:
        batch_record = connection.execute(
            """
            SELECT batch_id, base_result_version_id, classification_key
            FROM review_records WHERE batch_id = ?
            """,
            (batch["id"],),
        ).fetchone()
        legacy_record = connection.execute(
            "SELECT batch_id FROM review_records WHERE id = 'legacy-review'"
        ).fetchone()
    assert dict(batch_record) == {
        "batch_id": batch["id"],
        "base_result_version_id": base["version_id"],
        "classification_key": context.key,
    }
    assert legacy_record["batch_id"] is None


def test_version_lineage_counts_changed_label_and_missing_batch_history(
    tmp_path: Path,
) -> None:
    context, base = _publish_review_required(tmp_path)
    base_id = str(base["version_id"])
    result_service = ClassificationResultService(context.database)
    review_service = ReviewService(context.database, result_service)
    batch = review_service.create_batch(base_id, "user-1", "修正标签")
    review = review_service.batch_records(batch["id"])["items"][0]
    review_service.update_batch_record(
        batch["id"],
        review["id"],
        review["revision"],
        "user-1",
        "FIT_TOO_LARGE_U1",
        "确认应为尺码偏大",
    )
    derived = review_service.publish_batch(
        batch["id"],
        review_service.get_batch(batch["id"])["revision"],
        "user-1",
        "发布标签修正",
    )
    derived_id = str(derived["version_id"])

    assert derived["source_review_batch_id"] == batch["id"]
    assert derived["parent_version_no"] == 1
    assert derived["changed_unit_count"] == 1
    assert derived["inherited_unit_count"] == 0
    assert result_service.list()["items"][0]["changed_unit_count"] == 1
    assert result_service.history(derived_id)[0]["changed_unit_count"] == 1

    with context.database.transaction() as connection:
        connection.execute(
            """
            DELETE FROM review_revisions
            WHERE review_record_id IN (
                SELECT id FROM review_records WHERE batch_id = ?
            )
            """,
            (batch["id"],),
        )
        connection.execute(
            "DELETE FROM review_records WHERE batch_id = ?",
            (batch["id"],),
        )
        connection.execute(
            "DELETE FROM review_batches WHERE id = ?",
            (batch["id"],),
        )

    readable = result_service.get(derived_id)
    assert readable["source_review_batch_id"] is None
    assert readable["parent_version_no"] == 1
    assert readable["changed_unit_count"] == 0
    assert readable["inherited_unit_count"] == readable["unit_count"]
    assert result_service.history(derived_id)[0]["version_id"] == derived_id


def test_legacy_reviews_stay_legacy_and_new_batches_do_not_rebuild_task(
    tmp_path: Path,
) -> None:
    context, base = _publish_review_required(tmp_path)
    service = ReviewService(context.database)
    with context.database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO review_records(
                id, task_id, classification_key, comment,
                workflow_status, classification_json, updated_at
            ) VALUES ('legacy-review', ?, ?, '旧评论', 'pending', ?, ?)
            """,
            (
                context.task_id,
                context.key,
                json_text(context.results[context.key].model_dump(mode="json")),
                "2026-08-12T00:04:00+00:00",
            ),
        )
    batch = service.create_batch(str(base["version_id"]), "user-1", "新链路")

    legacy = service.list()
    assert [item["id"] for item in legacy] == ["legacy-review"]
    assert legacy[0]["legacy"] is True
    assert service.batch_records(batch["id"])["items"][0]["legacy"] is False


def test_legacy_resolve_rebuild_failure_restores_committed_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _base = _publish_review_required(tmp_path)
    service = ReviewService(context.database)
    original_classification = json_text(
        context.results[context.key].model_dump(mode="json")
    )
    original_state = {
        "workflow_status": "pending",
        "classification_json": original_classification,
        "revision": 7,
        "updated_by": "user-2",
        "updated_at": "2026-08-12T00:04:00+00:00",
    }
    with context.database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO review_records(
                id, task_id, classification_key, comment,
                workflow_status, classification_json, revision,
                updated_by, updated_at
            ) VALUES ('legacy-review-failure', ?, ?, '旧评论', ?, ?, ?, ?, ?)
            """,
            (
                context.task_id,
                context.key,
                *original_state.values(),
            ),
        )

    transaction_modes: list[bool] = []
    original_transaction = context.database.transaction

    def tracked_transaction(immediate: bool = False):
        transaction_modes.append(immediate)
        return original_transaction(immediate)

    committed_state: dict[str, object] = {}

    def fail_rebuild(_task_id: str, _actor_id: str) -> None:
        with context.database.connect() as connection:
            committed_state.update(
                dict(
                    connection.execute(
                        """
                        SELECT workflow_status, classification_json, revision,
                               updated_by, updated_at
                        FROM review_records WHERE id = 'legacy-review-failure'
                        """
                    ).fetchone()
                )
            )
            committed_state["revision_count"] = connection.execute(
                """
                SELECT COUNT(*) FROM review_revisions
                WHERE review_record_id = 'legacy-review-failure'
                """
            ).fetchone()[0]
        raise RuntimeError("模拟结果重建失败")

    monkeypatch.setattr(context.database, "transaction", tracked_transaction)
    monkeypatch.setattr(service, "_rebuild_result", fail_rebuild)
    selected_label = service.standard_service.combined_taxonomy().labels[0].code

    with pytest.raises(RuntimeError, match="模拟结果重建失败"):
        service.resolve(
            "legacy-review-failure",
            original_state["revision"],
            "user-1",
            selected_label,
            "验证补偿事务",
        )

    assert committed_state["workflow_status"] == "resolved"
    assert committed_state["classification_json"] != original_classification
    assert committed_state["revision"] == 8
    assert committed_state["updated_by"] == "user-1"
    assert committed_state["updated_at"] != original_state["updated_at"]
    assert committed_state["revision_count"] == 1
    assert transaction_modes == [True, True]

    with context.database.connect() as connection:
        restored = dict(
            connection.execute(
                """
                SELECT workflow_status, classification_json, revision,
                       updated_by, updated_at
                FROM review_records WHERE id = 'legacy-review-failure'
                """
            ).fetchone()
        )
        revision_count = connection.execute(
            """
            SELECT COUNT(*) FROM review_revisions
            WHERE review_record_id = 'legacy-review-failure'
            """
        ).fetchone()[0]
        success_audit_count = connection.execute(
            """
            SELECT COUNT(*) FROM audit_logs
            WHERE entity_type = 'review'
              AND entity_id = 'legacy-review-failure'
              AND action = 'resolve'
            """
        ).fetchone()[0]

    assert restored == original_state
    assert revision_count == 0
    assert success_audit_count == 0


def test_published_completed_with_errors_cannot_use_normal_retry(
    tmp_path: Path,
) -> None:
    context, _base = _publish_review_required(tmp_path)
    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE task_segments SET status = 'completed_with_errors'
            WHERE id = ?
            """,
            (context.segment_id,),
        )
    task = TaskService(context.database).get(context.task_id)
    with pytest.raises(ValueError, match="通过复核批次"):
        TaskService(context.database).retry_segment(
            context.task_id,
            "footwear",
            "user-1",
            task["revision"],
            "错误地重跑模型",
        )


def test_initialize_migrates_legacy_review_schema_before_batch_index(
    tmp_path: Path,
) -> None:
    context, base = _publish_review_required(tmp_path)
    _replace_with_legacy_review_schema(context)

    context.database.initialize()

    result_service = ClassificationResultService(context.database)
    review_service = ReviewService(context.database, result_service)
    app = FastAPI()

    def current_user() -> dict[str, str]:
        return {"id": "user-1"}

    app.include_router(
        create_review_router(review_service, context.database, current_user)
    )
    client = TestClient(app)
    created = client.post(
        f"/api/classification-results/{base['version_id']}/review-batches",
        json={"reason": "迁移后创建复核批次"},
    )
    assert created.status_code == 201
    batch_id = created.json()["id"]

    with context.database.connect() as connection:
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(review_records)"
            ).fetchall()
        }
        legacy = connection.execute(
            """
            SELECT batch_id, base_result_version_id, comment
            FROM review_records WHERE id = 'legacy-review'
            """
        ).fetchone()
        index = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'index' AND name = 'idx_review_records_batch'
            """
        ).fetchone()
    assert {"batch_id", "base_result_version_id"}.issubset(columns)
    assert dict(legacy) == {
        "batch_id": None,
        "base_result_version_id": None,
        "comment": "旧复核记录",
    }
    assert index["name"] == "idx_review_records_batch"
    assert review_service.list()[0]["legacy"] is True
    with context.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM review_revisions WHERE id = 'legacy-revision'"
            ).fetchone()[0]
            == 1
        )

    context.database.initialize()

    with context.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM review_records WHERE id = 'legacy-review'"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM review_batches WHERE id = ?",
                (batch_id,),
            ).fetchone()[0]
            == 1
        )
    assert client.get(f"/api/review-batches/{batch_id}").status_code == 200


def test_review_schema_migration_rolls_back_atomically_on_index_failure(
    tmp_path: Path,
) -> None:
    context, _base = _publish_review_required(tmp_path)
    _replace_with_legacy_review_schema(context)

    with context.database.connect() as connection:
        before_schema = [
            dict(row)
            for row in connection.execute(
                """
                SELECT type, name, tbl_name, sql FROM sqlite_master
                WHERE tbl_name IN ('review_records', 'review_revisions')
                ORDER BY type, name
                """
            ).fetchall()
        ]
        before_records = [
            tuple(row)
            for row in connection.execute(
                "SELECT * FROM review_records ORDER BY id"
            ).fetchall()
        ]
        before_revisions = [
            tuple(row)
            for row in connection.execute(
                "SELECT * FROM review_revisions ORDER BY id"
            ).fetchall()
        ]
        connection.executescript(
            """
            CREATE TABLE migration_fault_marker (
                id TEXT PRIMARY KEY,
                batch_id TEXT,
                updated_at TEXT
            );
            CREATE INDEX idx_review_records_batch
            ON migration_fault_marker(batch_id, updated_at DESC, id);
            """
        )

    with pytest.raises(sqlite3.OperationalError, match="already exists"):
        context.database.initialize()

    with context.database.connect() as connection:
        after_schema = [
            dict(row)
            for row in connection.execute(
                """
                SELECT type, name, tbl_name, sql FROM sqlite_master
                WHERE tbl_name IN ('review_records', 'review_revisions')
                ORDER BY type, name
                """
            ).fetchall()
        ]
        after_records = [
            tuple(row)
            for row in connection.execute(
                "SELECT * FROM review_records ORDER BY id"
            ).fetchall()
        ]
        after_revisions = [
            tuple(row)
            for row in connection.execute(
                "SELECT * FROM review_revisions ORDER BY id"
            ).fetchall()
        ]
        legacy_tables = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name LIKE 'legacy_review_%'
            """
        ).fetchall()
        foreign_keys_enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    assert after_schema == before_schema
    assert after_records == before_records
    assert after_revisions == before_revisions
    assert legacy_tables == []
    assert foreign_keys_enabled == 1

    with context.database.connect() as connection:
        connection.execute("DROP INDEX idx_review_records_batch")
        connection.execute("DROP TABLE migration_fault_marker")
    context.database.initialize()
    context.database.initialize()

    with context.database.connect() as connection:
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(review_records)"
            ).fetchall()
        }
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM review_records WHERE id = 'legacy-review'"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM review_revisions WHERE id = 'legacy-revision'"
            ).fetchone()[0]
            == 1
        )
    assert {"batch_id", "base_result_version_id"}.issubset(columns)


def test_initialize_recovers_orphan_publishing_status(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE task_segments
            SET status = 'completed', result_publish_status = 'publishing'
            WHERE id = ?
            """,
            (context.segment_id,),
        )
    context.database.initialize()

    with context.database.connect() as connection:
        segment = connection.execute(
            """
            SELECT status, result_publish_status, result_publish_error
            FROM task_segments WHERE id = ?
            """,
            (context.segment_id,),
        ).fetchone()
    assert segment["status"] == "completed"
    assert segment["result_publish_status"] == "failed"
    assert "重试发布" in segment["result_publish_error"]
