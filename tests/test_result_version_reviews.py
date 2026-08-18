from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_classification_result_pool import _publish, _seed_result_context

from return_semantics.schemas import ProcessingStatus
from web_backend.classification_result_service import ClassificationResultService
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
    with context.database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO users(id, email, display_name, password_hash, created_at)
            VALUES ('user-2', 'two@example.com', '用户二', 'hash', ?)
            """,
            ("2026-08-12T00:03:00+00:00",),
        )
    return context, version


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
            worker=SimpleNamespace(is_alive=True),
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
        "FIT_TOO_SMALL",
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
            "FIT_TOO_SMALL",
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

    assert derived["version"] == 2
    assert derived["parent_version_id"] == base_id
    assert derived["version_reason"] == "发布人工确认结果"
    assert derived["created_by"] == "user-1"
    assert derived["created_by_name"] == "用户一"
    assert derived["source_review_batch_id"] == batch["id"]
    assert derived["parent_version_no"] == 1
    assert derived["changed_unit_count"] == 0
    assert derived["inherited_unit_count"] == 1
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
        assert revised["classification"]["semantic_units"][0]["evidence"] == (
            original["classification"]["semantic_units"][0]["evidence"]
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
        assert connection.execute(
            "SELECT COUNT(*) FROM classification_result_versions"
        ).fetchone()[0] == 2
        actions = {
            row["action"]
            for row in connection.execute(
                "SELECT action FROM audit_logs WHERE entity_id = ?",
                (batch["id"],),
            ).fetchall()
        }
    assert {"create", "update_record", "publish", "conflict"}.issubset(actions)


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
            "label_code": "FIT_TOO_SMALL",
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
    history = client.get(
        f"/api/classification-results/{base['version_id']}/versions"
    )
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
    record = client.get(
        f"/api/review-batches/{batch['id']}/records"
    ).json()["items"][0]

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
    excluded = client.get(
        f"/api/review-batches/{batch['id']}/records"
    ).json()["items"][0]
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
    assert {
        item["quality_status"] for item in derived_records["items"]
    } == {"excluded"}
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
        "FIT_TOO_LARGE",
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
        assert connection.execute(
            "SELECT COUNT(*) FROM review_revisions WHERE id = 'legacy-revision'"
        ).fetchone()[0] == 1

    context.database.initialize()

    with context.database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM review_records WHERE id = 'legacy-review'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM review_batches WHERE id = ?",
            (batch_id,),
        ).fetchone()[0] == 1
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
        foreign_keys_enabled = connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]
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
        assert connection.execute(
            "SELECT COUNT(*) FROM review_records WHERE id = 'legacy-review'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM review_revisions WHERE id = 'legacy-revision'"
        ).fetchone()[0] == 1
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
