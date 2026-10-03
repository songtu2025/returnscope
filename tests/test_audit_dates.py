from pathlib import Path

import pytest
from test_classification_result_pool import _seed_result_context

from web_backend.operations_service import AuditLogService


def test_audit_date_only_includes_whole_day_and_iso_is_exact(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    with context.database.transaction() as connection:
        for audit_id, created_at in (
            ("audit-day-start", "2026-08-12T00:00:00+00:00"),
            ("audit-day-late", "2026-08-12T18:30:00+00:00"),
            ("audit-next-day", "2026-08-13T00:00:00+00:00"),
        ):
            connection.execute(
                """
                INSERT INTO audit_logs(
                    id, entity_type, entity_id, action, actor_id, created_at
                ) VALUES (?, 'date_case', ?, 'inspect', 'user-1', ?)
                """,
                (audit_id, audit_id, created_at),
            )
    service = AuditLogService(context.database)

    whole_day = service.list(
        entity_type="date_case",
        date_from="2026-08-12",
        date_to="2026-08-12",
    )
    assert whole_day["total"] == 2
    assert {item["id"] for item in whole_day["items"]} == {
        "audit-day-start",
        "audit-day-late",
    }
    exact = service.list(
        entity_type="date_case",
        date_from="2026-08-12T18:30:00+00:00",
        date_to="2026-08-12T18:30:00+00:00",
    )
    assert [item["id"] for item in exact["items"]] == ["audit-day-late"]
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        service.list(date_to="2026-02-30")


@pytest.mark.parametrize(
    "value,is_end,expected,inclusive",
    [
        ("2026-08-12", False, "2026-08-12T00:00:00+00:00", False),
        ("2026-08-12", True, "2026-08-13T00:00:00+00:00", False),
        (" 2026-08-12 ", False, "2026-08-12T00:00:00+00:00", False),
        ("2026-08-12T18:30:00Z", True, "2026-08-12T18:30:00+00:00", True),
        ("2026-08-12T20:30:00+02:00", False, "2026-08-12T18:30:00+00:00", True),
        ("2026-08-12T18:30:00", False, "2026-08-12T18:30:00", True),
    ],
)
def test_audit_date_boundary_preserves_normalization_and_inclusivity(
    value: str, is_end: bool, expected: str, inclusive: bool
) -> None:
    assert AuditLogService._date_boundary(value, is_end=is_end) == (
        expected,
        inclusive,
    )


@pytest.mark.parametrize("value", ["2026-02-30", "invalid", ""])
@pytest.mark.parametrize("is_end", [False, True])
def test_invalid_audit_date_keeps_validation_message(value: str, is_end: bool) -> None:
    with pytest.raises(ValueError) as raised:
        AuditLogService._date_boundary(value, is_end=is_end)
    assert str(raised.value) == "审计日期必须是 YYYY-MM-DD 或 ISO 时间戳"
