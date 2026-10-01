from copy import deepcopy
from typing import Any

import pytest

from web_backend.operations_service import AuditLogService

TARGET_CASES = (
    ("task", {}, {"route": "tasks", "task_id": "entity-1"}),
    (
        "task_segment",
        {"task_id": "task-1"},
        {"route": "tasks", "task_id": "task-1", "segment_id": "entity-1"},
    ),
    (
        "classification_result_version",
        {},
        {"route": "classification-results", "result_version_id": "entity-1"},
    ),
    (
        "classification_result",
        {"result_version_id": "version-1"},
        {"route": "classification-results", "result_version_id": "version-1"},
    ),
    (
        "review",
        {"workflow_status": "resolved"},
        {"route": "review", "review_id": "entity-1", "workflow_status": "resolved"},
    ),
    ("review_batch", {}, {"route": "review-center", "batch_id": "entity-1"}),
    (
        "dataset",
        {"kind": "products"},
        {"route": "data", "dataset_id": "entity-1", "view": "products"},
    ),
    (
        "api_connection",
        {},
        {"route": "api", "tab": "api", "connection_id": "entity-1"},
    ),
    (
        "api_config_version",
        {"connection_id": "connection-1"},
        {
            "route": "api",
            "tab": "api",
            "connection_id": "connection-1",
            "config_version_id": "entity-1",
        },
    ),
    (
        "api_model",
        {"connection_id": "connection-1"},
        {
            "route": "api",
            "tab": "models",
            "connection_id": "connection-1",
            "model_id": "entity-1",
        },
    ),
    ("user", {}, {"route": "team", "tab": "users", "user_id": "entity-1"}),
    (
        "analysis_dashboard",
        {"current_version_id": "version-1"},
        {
            "route": "analysis-dashboards",
            "dashboard_id": "entity-1",
            "version_id": "version-1",
        },
    ),
)


@pytest.mark.parametrize("entity_type,source,expected", TARGET_CASES)
def test_audit_target_preserves_fields_and_does_not_share_mutable_results(
    entity_type: str,
    source: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    context = {(entity_type, "entity-1"): deepcopy(source)}
    before = deepcopy(context)

    target = AuditLogService._target(entity_type, "entity-1", context)

    assert target == expected
    assert target is not None
    target["route"] = "changed-by-caller"
    assert AuditLogService._target(entity_type, "entity-1", context) == expected
    assert context == before


@pytest.mark.parametrize("entity_type,source,_expected", TARGET_CASES)
@pytest.mark.parametrize("matching_id", [False, True])
def test_audit_target_requires_matching_entity_context(
    entity_type: str,
    source: dict[str, Any],
    _expected: dict[str, Any],
    matching_id: bool,
) -> None:
    context = (
        {(entity_type, "entity-1"): None}
        if matching_id
        else {(entity_type, "other-entity"): source}
    )

    assert AuditLogService._target(entity_type, "entity-1", context) is None


@pytest.mark.parametrize(
    "version_id,expected",
    [
        (None, {"route": "analysis-dashboards", "dashboard_id": "dashboard-1"}),
        ("", {"route": "analysis-dashboards", "dashboard_id": "dashboard-1"}),
        (False, {"route": "analysis-dashboards", "dashboard_id": "dashboard-1"}),
        (
            "version-next",
            {
                "route": "analysis-dashboards",
                "dashboard_id": "dashboard-1",
                "version_id": "version-next",
            },
        ),
        (
            17,
            {
                "route": "analysis-dashboards",
                "dashboard_id": "dashboard-1",
                "version_id": 17,
            },
        ),
    ],
)
def test_audit_dashboard_target_preserves_version_truthiness(
    version_id: Any,
    expected: dict[str, Any],
) -> None:
    context = {
        ("analysis_dashboard", "dashboard-1"): {"current_version_id": version_id}
    }

    assert (
        AuditLogService._target("analysis_dashboard", "dashboard-1", context)
        == expected
    )


@pytest.mark.parametrize(
    "entity_type,missing_field",
    [
        ("task_segment", "task_id"),
        ("classification_result", "result_version_id"),
        ("review", "workflow_status"),
        ("dataset", "kind"),
        ("api_config_version", "connection_id"),
        ("api_model", "connection_id"),
        ("analysis_dashboard", "current_version_id"),
    ],
)
def test_audit_target_does_not_hide_invalid_source_fields(
    entity_type: str,
    missing_field: str,
) -> None:
    with pytest.raises(KeyError) as raised:
        AuditLogService._target(
            entity_type, "entity-1", {(entity_type, "entity-1"): {}}
        )

    assert raised.value.args == (missing_field,)


@pytest.mark.parametrize("source", [None, {}])
def test_unknown_audit_entity_has_no_navigation_target(
    source: dict[str, Any] | None,
) -> None:
    context = {("unknown", "entity-1"): source}

    assert AuditLogService._target("unknown", "entity-1", context) is None
