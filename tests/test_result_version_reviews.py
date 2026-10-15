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
from historical_review_fixtures import historical_batch
from test_classification_result_pool import _publish, _seed_result_context

from return_semantics.schemas import ProcessingStatus
from web_backend import review_service as review_service_module
from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.common import json_text
from web_backend.review_service import (
    ReviewBatchConflict,
    ReviewService,
    RevisionConflict,
)
from web_backend.routers.accounts import create_account_router
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
        "list_batches": "(self, *, page: int = 1, page_size: int = 50, status: str | None = None, base_result_version_id: str | None = None, q: str | None = None) -> dict[str, typing.Any]",
        "get_batch": "(self, batch_id: str) -> dict[str, typing.Any]",
        "batch_records": "(self, batch_id: str, *, page: int = 1, page_size: int = 50, workflow_status: str | None = None, q: str | None = None, listing: str | None = None, product_name: str | None = None, product_sku: str | None = None, order_id: str | None = None) -> dict[str, typing.Any]",
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
        "_validate_reviewed_classification",
        "_top_problem_labels",
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
        "POST|/api/classification-results/{version_id}/review-batches|create_review_batch|410|version_id,user",
        "GET|/api/review-batches|list_review_batches|200|_user,page,page_size,status,base_result_version_id,q",
        "GET|/api/review-batches/{batch_id}|get_review_batch|200|batch_id,_user",
        "GET|/api/review-batches/{batch_id}/records|list_review_batch_records|200|batch_id,_user,page,page_size,workflow_status,q,listing,product_name,product_sku,order_id",
        "PATCH|/api/review-batches/{batch_id}/records/{review_id}|update_review_batch_record|410|batch_id,review_id,user",
        "PATCH|/api/review-batches/{batch_id}/records|update_review_batch_records|410|batch_id,user",
        "POST|/api/review-batches/{batch_id}/publish|publish_review_batch|410|batch_id,user",
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
    historical_batch(context, base)
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
            export_worker=SimpleNamespace(
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


def test_initialize_repairs_empty_draft_review_batch(tmp_path: Path) -> None:
    context, base = _publish_review_required(tmp_path)
    review_service = ReviewService(context.database)
    batch = historical_batch(context, base)
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
    batch = historical_batch(context, base)

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
    with pytest.raises(ValueError, match="查看证据并人工修正"):
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
    assert created.status_code == 410
    batch_id = historical_batch(context, base)["id"]

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


@pytest.mark.parametrize("production", [False, True])
def test_initialize_recovers_orphan_publishing_status(
    tmp_path: Path, production: bool
) -> None:
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
    context.database.initialize(production=production)

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


def test_initialize_skips_publishing_recovery_after_migration_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _seed_result_context(tmp_path)
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET result_publish_status = 'publishing' WHERE id = ?",
            (context.segment_id,),
        )

    def fail_migration(_connection: sqlite3.Connection) -> None:
        raise RuntimeError("模拟迁移失败")

    monkeypatch.setattr(
        type(context.database),
        "_migrate_ai_insight_reports",
        staticmethod(fail_migration),
    )
    with pytest.raises(RuntimeError, match="模拟迁移失败"):
        context.database.initialize()

    with context.database.connect() as connection:
        status = connection.execute(
            "SELECT result_publish_status FROM task_segments WHERE id = ?",
            (context.segment_id,),
        ).fetchone()[0]
    assert status == "publishing"
