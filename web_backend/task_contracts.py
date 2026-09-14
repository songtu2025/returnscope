from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ACTIVE_STATUSES = {"queued", "running", "paused"}
FINAL_STATUSES = {"completed", "failed", "cancelled", "blocked", "partial"}
WAITING_SEGMENT_STATUSES = {"queued", "retry_pending"}
SEGMENT_USER_LIMIT = 3


class TaskRevisionConflict(ValueError):
    pass


class TaskPlanConflict(ValueError):
    pass


class TaskResultPublishConflict(ValueError):
    pass


@dataclass(frozen=True)
class _ReplanSegmentSyncContext:
    prepared: Any
    old_segments: list[Any]
    preserved: dict[str, Any]
    planned_segments: dict[str, Any]
    planned_keys: dict[str, list[str]]
    record_counts: Any
    current_hash: str
    unresolved_policy: str
    now: str
