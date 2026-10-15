"""人工修正烟测必须核对真实父版本和审计关联，历史批次参数仍兼容。"""

from dataclasses import replace

import pytest
from test_smoke_web_business import smoke_scope as smoke_scope
from test_smoke_web_business import smoke_transport as smoke_transport

from scripts import smoke_web_business as business
from scripts.smoke_web_production import SmokeClient


@pytest.fixture
def direct_scope(smoke_scope, smoke_transport):
    payloads = smoke_transport.payloads
    payloads["/api/classification-results/result-2"].update(
        source_review_batch_id=None, result_id="result-group", version=2
    )
    payloads["/api/classification-results/result-1"] = {
        "version_id": "result-1",
        "result_id": "result-group",
        "publish_status": "published",
        "version": 1,
    }
    payloads["/api/audit/classification_result/result-group"] = [
        {
            "action": "manual_correction",
            "actor_name": "合成操作员",
            "created_at": "2026-10-15T00:00:00Z",
            "before": {"version_id": "result-1"},
            "after": {"version_id": "result-2"},
        }
    ]
    return replace(smoke_scope, review_batch_id="")


def test_direct_correction_smoke_checks_parent_and_audit_without_batch_writes(
    direct_scope, smoke_transport, capsys
):
    business.check_business(SmokeClient("https://smoke.example.test"), direct_scope)
    assert "人工修正审计与父版本" in capsys.readouterr().out
    assert all(method == "GET" for method, _ in smoke_transport.calls)
    assert not any("review-batches" in path for _, path in smoke_transport.calls)
    assert ("GET", "/api/classification-results/result-1") in smoke_transport.calls
    assert (
        "GET",
        "/api/audit/classification_result/result-group",
    ) in smoke_transport.calls


@pytest.mark.parametrize(
    "problem",
    [
        "missing_audit",
        "wrong_parent",
        "wrong_version",
        "missing_actor",
        "missing_time",
        "foreign_result",
    ],
)
def test_direct_smoke_rejects_incomplete_or_foreign_correction(
    direct_scope, smoke_transport, problem
):
    payloads = smoke_transport.payloads
    audits = payloads["/api/audit/classification_result/result-group"]
    if problem == "missing_audit":
        audits.clear()
    elif problem == "wrong_parent":
        audits[0]["before"]["version_id"] = "foreign-parent"
    elif problem == "wrong_version":
        audits[0]["after"]["version_id"] = "foreign-version"
    elif problem == "missing_actor":
        audits[0]["actor_name"] = ""
    elif problem == "missing_time":
        audits[0]["created_at"] = ""
    else:
        payloads["/api/classification-results/result-1"]["result_id"] = "foreign-result"
    with pytest.raises(RuntimeError, match="人工修正"):
        business.check_business(SmokeClient("https://smoke.example.test"), direct_scope)
