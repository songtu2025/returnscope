from __future__ import annotations

import json
import urllib.error
from contextlib import contextmanager
from email.message import Message
from types import SimpleNamespace

import pytest

from scripts import smoke_web_business as business
from scripts.smoke_web_production import SmokeClient


@pytest.fixture
def smoke_scope():
    return business.BusinessScope(
        "result-2", "batch-1", "dashboard-1", "dv-2", "report-1"
    )


@pytest.fixture
def smoke_transport(monkeypatch):
    headers = Message()
    headers["Set-Cookie"] = "session=synthetic-cookie; HttpOnly; SameSite=lax; Secure"
    payloads = {
        "/api/auth/login": {"id": "user-1"},
        "/api/auth/me": {"email": "smoke@example.test"},
        "/api/auth/logout": None,
        "/api/classification-results/result-2": {
            "version_id": "result-2",
            "publish_status": "published",
            "source_review_batch_id": "batch-1",
            "parent_version_id": "result-1",
            "record_count": 2,
        },
        "/api/classification-results/result-2/records?page_size=1": {
            "total": 2,
            "items": [{"result_version_id": "result-2"}],
        },
        "/api/classification-results/result-2/summary": {
            "version_id": "result-2",
            "metrics": {"source_record_count": 2},
        },
        "/api/review-batches/batch-1": {
            "id": "batch-1",
            "status": "published",
            "published_version_id": "result-2",
            "base_result_version_id": "result-1",
            "remaining_count": 0,
        },
        "/api/analysis-dashboards/dashboard-1?version_id=dv-2": {
            "id": "dashboard-1",
            "version": {
                "version_id": "dv-2",
                "filters": {},
                "source_snapshot": [{"result_version_id": "result-2"}],
                "summary": {"record_count": 2},
            },
        },
        "/api/analysis-dashboards/dashboard-1/versions/dv-2/sources": [
            {"result_version_id": "result-2"},
        ],
        "/api/analysis-dashboards/dashboard-1/versions/dv-2/summary": {
            "dashboard_id": "dashboard-1",
            "version_id": "dv-2",
            "record_count": 2,
        },
        "/api/analysis-dashboards/dashboard-1/versions/dv-2/records?page_size=1": {
            "total": 2,
        },
        "/api/ai-insight-reports/report-1": {
            "id": "report-1",
            "status": "completed",
            "dashboard_id": "dashboard-1",
            "dashboard_version_id": "dv-2",
            "evidence": {
                "source": {
                    "dashboard_id": "dashboard-1",
                    "dashboard_version_id": "dv-2",
                },
            },
            "content": {"narrative": "synthetic-business-body"},
        },
    }
    calls = []

    @contextmanager
    def open_request(request, timeout):
        path = request.full_url.removeprefix("https://smoke.example.test")
        calls.append((request.get_method(), path))
        value = payloads[path]
        if isinstance(value, Exception):
            raise value
        yield SimpleNamespace(
            status=204 if path == "/api/auth/logout" else 200,
            headers=headers,
            read=lambda: json.dumps(value).encode(),
        )

    monkeypatch.setattr(
        "urllib.request.build_opener", lambda *args: SimpleNamespace(open=open_request)
    )
    return SimpleNamespace(payloads=payloads, calls=calls, headers=headers)


def test_business_smoke_checks_scope_without_business_writes(
    smoke_scope, smoke_transport, capsys
):
    business.run_smoke(
        "https://smoke.example.test",
        "smoke@example.test",
        "synthetic-password",
        smoke_scope,
    )
    assert len(smoke_transport.calls) == 12
    assert [path for method, path in smoke_transport.calls if method != "GET"] == [
        "/api/auth/login",
        "/api/auth/logout",
    ]
    output = capsys.readouterr().out
    assert output.count("[通过]") == 6
    for value in ("synthetic-password", "synthetic-cookie", "synthetic-business-body"):
        assert value not in output


def test_feedback_group_count_can_differ_from_source_rows(smoke_scope, smoke_transport):
    summary = {"record_count": 1, "counting_basis": "feedback_group"}
    smoke_transport.payloads["/api/analysis-dashboards/dashboard-1?version_id=dv-2"][
        "version"
    ]["summary"] = summary
    smoke_transport.payloads[
        "/api/analysis-dashboards/dashboard-1/versions/dv-2/summary"
    ].update(summary)
    business.check_business(SmokeClient("https://smoke.example.test"), smoke_scope)


@pytest.mark.parametrize(
    "path,fields,replacement",
    [
        ("/api/classification-results/result-2", ["version_id"], "other-result"),
        ("/api/classification-results/result-2", ["record_count"], 0),
        (
            "/api/classification-results/result-2/summary",
            ["metrics", "source_record_count"],
            9,
        ),
        ("/api/review-batches/batch-1", ["published_version_id"], "other-result"),
        ("/api/review-batches/batch-1", ["base_result_version_id"], "other-base"),
        ("/api/review-batches/batch-1", ["remaining_count"], 1),
        (
            "/api/analysis-dashboards/dashboard-1?version_id=dv-2",
            ["version", "version_id"],
            "other-version",
        ),
        (
            "/api/analysis-dashboards/dashboard-1?version_id=dv-2",
            ["version", "source_snapshot"],
            [],
        ),
        (
            "/api/analysis-dashboards/dashboard-1?version_id=dv-2",
            ["version", "filters"],
            {"listing": "other"},
        ),
        (
            "/api/analysis-dashboards/dashboard-1/versions/dv-2/summary",
            ["record_count"],
            9,
        ),
        (
            "/api/analysis-dashboards/dashboard-1/versions/dv-2/summary",
            ["version_id"],
            "other-version",
        ),
        (
            "/api/analysis-dashboards/dashboard-1/versions/dv-2/summary",
            ["counting_basis"],
            "unknown-basis",
        ),
        (
            "/api/analysis-dashboards/dashboard-1?version_id=dv-2",
            ["version", "summary", "record_count"],
            1,
        ),
        ("/api/ai-insight-reports/report-1", ["status"], "running"),
        ("/api/ai-insight-reports/report-1", ["dashboard_version_id"], "other-version"),
        (
            "/api/ai-insight-reports/report-1",
            ["evidence", "source", "dashboard_version_id"],
            "other-version",
        ),
        ("/api/ai-insight-reports/report-1", ["evidence"], None),
    ],
)
def test_business_smoke_rejects_scope_or_payload_errors(
    smoke_scope, smoke_transport, path, fields, replacement
):
    value = smoke_transport.payloads[path]
    for field in fields[:-1]:
        value = value[field]
    value[fields[-1]] = replacement
    with pytest.raises(RuntimeError):
        business.run_smoke(
            "https://smoke.example.test",
            "smoke@example.test",
            "synthetic-password",
            smoke_scope,
        )
    assert smoke_transport.calls[-1] == ("POST", "/api/auth/logout")


@pytest.mark.parametrize("code", [401, 403, 404, 500])
def test_http_failure_redacts_body_and_closes_session(
    smoke_scope, smoke_transport, code, capsys
):
    from io import BytesIO

    smoke_transport.payloads["/api/classification-results/result-2"] = (
        urllib.error.HTTPError(
            "https://smoke.example.test",
            code,
            "synthetic-sensitive-message",
            Message(),
            BytesIO(b"synthetic-password synthetic-cookie synthetic-business-body"),
        )
    )
    with pytest.raises(RuntimeError, match=f"返回 {code}") as error:
        business.run_smoke(
            "https://smoke.example.test",
            "smoke@example.test",
            "synthetic-password",
            smoke_scope,
        )
    assert error.value.__suppress_context__ is True
    assert "synthetic-" not in str(error.value) + capsys.readouterr().out
    assert smoke_transport.calls[-1] == ("POST", "/api/auth/logout")


@pytest.mark.parametrize(
    "cookie", ["session=synthetic-cookie", "session=x; HttpOnly; SameSite=lax"]
)
def test_https_login_requires_cookie_security_flags(smoke_transport, cookie):
    smoke_transport.headers.replace_header("Set-Cookie", cookie)
    with pytest.raises(RuntimeError, match="安全属性"):
        SmokeClient("https://smoke.example.test").login(
            "smoke@example.test", "synthetic-password"
        )


def test_login_rejects_wrong_identity(smoke_transport):
    smoke_transport.payloads["/api/auth/me"]["email"] = "other@example.test"
    with pytest.raises(RuntimeError, match="身份校验"):
        SmokeClient("https://smoke.example.test").login(
            "smoke@example.test", "synthetic-password"
        )


def test_invalid_json_redacts_original_body(smoke_transport, monkeypatch):
    client = SmokeClient("https://smoke.example.test")
    monkeypatch.setattr(
        client, "request", lambda *args: (200, Message(), b"synthetic-business-body")
    )
    with pytest.raises(RuntimeError, match="有效 JSON") as error:
        client.json("/api/ai-insight-reports/report-1")
    assert error.value.__suppress_context__ is True
    assert "synthetic-business-body" not in str(error.value)


def test_connection_error_does_not_expose_reason(smoke_transport):
    smoke_transport.payloads["/api/auth/me"] = urllib.error.URLError(
        "synthetic-password"
    )
    with pytest.raises(RuntimeError, match="无法连接") as error:
        SmokeClient("https://smoke.example.test").json("/api/auth/me")
    assert error.value.__suppress_context__ is True
    assert "synthetic-password" not in str(error.value)
