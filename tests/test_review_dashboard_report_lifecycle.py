"""直接人工修正与报告的来源一致性回归。"""

from pathlib import Path
from types import SimpleNamespace

import pytest
import test_insight_reports
from test_manual_correction import _items, _record
from test_result_version_reviews import _publish_review_required

from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_results.manual_correction import correct_group


@pytest.fixture
def lifecycle(tmp_path, monkeypatch):
    context, base = _publish_review_required(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(test_insight_reports, "_seed_result_context", lambda _: context)
        patch.setattr(test_insight_reports, "_publish", lambda _: base)
        _, dashboard, reports, captured = test_insight_reports._service_context(
            tmp_path, filters={"quality_status": ["ready", "review_required"]}
        )
    return SimpleNamespace(
        context=context,
        database=context.database,
        base=base,
        results=ClassificationResultService(context.database),
        dashboard=dashboard,
        dashboards=reports.dashboard_service,
        reports=reports,
        captured=captured,
    )


def test_manual_correction_marks_reports_stale_without_regeneration(
    tmp_path: Path, monkeypatch
):
    import test_insight_reports
    from test_insight_reports import _complete_report

    context, version = _publish_review_required(tmp_path)
    monkeypatch.setattr(test_insight_reports, "_seed_result_context", lambda _: context)
    monkeypatch.setattr(test_insight_reports, "_publish", lambda _: version)
    _, board, reports, captured = test_insight_reports._service_context(
        tmp_path, filters={"quality_status": ["ready", "review_required"]}
    )
    old = _complete_report(board, reports)
    assert not old["source_outdated"]
    messages = captured["messages"]
    corrected = correct_group(
        ClassificationResultService(context.database),
        version["version_id"],
        _record(context, version),
        _items(),
        "user-2",
    )
    current = reports.dashboard_service.get(board["id"])
    stale = reports.get(old["id"])
    assert stale["source_outdated"]
    assert stale["content"] == old["content"]
    assert stale["evidence"] == old["evidence"]
    assert captured["messages"] is messages
    assert (
        reports.list(board["id"], current["version"]["version_id"])[0]["id"]
        == old["id"]
    )
    latest = _complete_report(current, reports)
    assert not latest["source_outdated"]
    assert (
        current["version"]["source_snapshot"][0]["result_version_id"]
        == corrected["version_id"]
    )


def test_report_generation_keeps_one_source_when_manual_result_changes(
    tmp_path: Path, monkeypatch
):
    import test_insight_reports

    context, version = _publish_review_required(tmp_path)
    monkeypatch.setattr(test_insight_reports, "_seed_result_context", lambda _: context)
    monkeypatch.setattr(test_insight_reports, "_publish", lambda _: version)
    _, board, reports, _ = test_insight_reports._service_context(
        tmp_path, filters={"quality_status": ["ready", "review_required"]}
    )
    queued = reports.create_for_dashboard(
        board["id"],
        board["version"]["version_id"],
        model_id="model-1",
        reasoning_effort="high",
        actor_id="user-1",
    )
    assert reports.claim_next() == queued["id"]
    factory = reports.client_factory

    def changing_client(settings):
        client = factory(settings)
        generate = client.generate_json

        def generate_json(*args, **kwargs):
            correct_group(
                ClassificationResultService(context.database),
                version["version_id"],
                _record(context, version),
                _items(),
                "user-2",
            )
            return generate(*args, **kwargs)

        client.generate_json = generate_json
        return client

    reports.client_factory = changing_client
    reports.run(queued["id"])
    completed = reports.get(queued["id"])
    assert completed["status"] == "completed"
    assert completed["source_outdated"]
    assert completed["dashboard_version_id"] == board["version"]["version_id"]
    assert (
        completed["evidence"]["source"]["dashboard_version_id"]
        == board["version"]["version_id"]
    )
