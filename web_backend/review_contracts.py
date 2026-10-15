from __future__ import annotations

import threading

_TASK_LOCKS: dict[str, threading.Lock] = {}

_LOCKS_GUARD = threading.Lock()


def _task_lock(task_id: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _TASK_LOCKS.setdefault(task_id, threading.Lock())


class RevisionConflict(ValueError):
    pass


class ReviewBatchConflict(ValueError):
    pass


LEGACY_REVIEW_BATCH_MESSAGE = "复核批次编辑与发布已停用，请在分类结果中直接人工修正语义"


class LegacyReviewBatchClosed(ValueError):
    def __init__(self) -> None:
        super().__init__(LEGACY_REVIEW_BATCH_MESSAGE)
