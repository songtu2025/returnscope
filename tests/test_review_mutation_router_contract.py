"""退役批次写入口必须同时阻断 HTTP 和服务调用，且不改变历史数据。"""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from historical_review_fixtures import historical_batch
from test_manual_correction import _items, _record
from test_result_version_reviews import _publish_review_required

from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_results.manual_correction import correct_group
from web_backend.review_contracts import (
    LEGACY_REVIEW_BATCH_MESSAGE,
    LegacyReviewBatchClosed,
)
from web_backend.review_service import ReviewService
from web_backend.routers.reviews import create_review_router

WRITES = [
    ("POST", "/api/classification-results/base/review-batches"),
    ("PATCH", "/api/review-batches/historical-batch/records/historical-review"),
    ("PATCH", "/api/review-batches/historical-batch/records"),
    ("POST", "/api/review-batches/historical-batch/publish"),
]


@pytest.mark.parametrize("method,path", WRITES)
@pytest.mark.parametrize(
    "payload", [None, {}, {"expected_revision": 1, "reason": "合成旧请求"}]
)
def test_retired_batch_http_rejects_authenticated_writes_without_changes(
    tmp_path, method, path, payload
):
    context, base = _publish_review_required(tmp_path)
    historical_batch(context, base)
    service = ReviewService(context.database)
    authenticated = False

    def user():
        if not authenticated:
            raise HTTPException(status_code=401, detail="请登录")
        return {"id": "user-1"}

    app = FastAPI()
    app.include_router(create_review_router(service, context.database, user))
    client = TestClient(app)
    with context.database.connect() as connection:
        before = list(connection.iterdump())
    assert client.request(method, path, json=payload).status_code == 401
    authenticated = True
    response = client.request(method, path, json=payload)
    assert response.status_code == 410
    assert response.json() == {"detail": LEGACY_REVIEW_BATCH_MESSAGE}
    assert (
        client.get("/api/review-batches/historical-batch").json()["record_count"] == 1
    )
    assert (
        client.get("/api/review-batches/historical-batch/records").json()["total"] == 1
    )
    with context.database.connect() as connection:
        assert list(connection.iterdump()) == before


@pytest.mark.parametrize(
    "method,args",
    [
        ("create_batch", ("base", "user-1", "")),
        ("update_batch_record", ("batch", "review", 1, "user-1", None, "")),
        ("update_batch_records", ("batch", [], "user-1", "confirm", None, "")),
        ("publish_batch", ("batch", 1, "user-1", "")),
    ],
)
def test_retired_batch_service_cannot_bypass_http(method, args):
    # 不提供数据库，证明旧入口在任何持久化访问前拒绝执行。
    service = object.__new__(ReviewService)
    with pytest.raises(LegacyReviewBatchClosed, match="已停用"):
        getattr(service, method)(*args)


def test_direct_manual_correction_remains_available_with_historical_batches(tmp_path):
    context, base = _publish_review_required(tmp_path)
    batch = historical_batch(context, base)
    service = ClassificationResultService(context.database)
    changed = correct_group(
        service, base["version_id"], _record(context, base), _items(), "user-2"
    )
    assert changed["version_id"] != base["version_id"]
    history = ReviewService(context.database).get_batch(batch["id"])
    assert history["record_count"] == 1
    assert history["revision"] == batch["revision"]
    with context.database.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM review_batches").fetchone()[0] == 1
        )
