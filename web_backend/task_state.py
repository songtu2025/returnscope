from __future__ import annotations


def summarize_task_status(statuses: list[str]) -> str:
    if not statuses:
        return "blocked"
    if any(status in {"running", "pausing", "cancelling"} for status in statuses):
        return "running"
    if any(status in {"queued", "retry_pending"} for status in statuses):
        return "queued"
    if all(status == "completed" for status in statuses):
        return "completed"
    if any(status == "paused" for status in statuses):
        return "paused"
    has_deliverable = any(
        status in {"completed", "completed_with_errors"}
        for status in statuses
    )
    if has_deliverable:
        return "partial"
    if all(status == "cancelled" for status in statuses):
        return "cancelled"
    return "blocked"
