from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

_TASK_LOCKS: dict[str, threading.Lock] = {}

_LOCKS_GUARD = threading.Lock()


def _task_lock(task_id: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _TASK_LOCKS.setdefault(task_id, threading.Lock())


class RevisionConflict(ValueError):
    pass


class ReviewBatchConflict(ValueError):
    pass


@dataclass(frozen=True)
class _BatchPublishRequest:
    batch_id: str
    expected_revision: int
    actor_id: str
    reason: str
    now: str


@dataclass(frozen=True)
class _CompletedReviewChanges:
    revisions: dict[str, dict[str, Any]]
    excluded_keys: set[str]


@dataclass(frozen=True)
class _DerivedResultContent:
    units: list[dict[str, Any]]
    labels: list[dict[str, Any]]
    records: list[dict[str, Any]]
