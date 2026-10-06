from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from return_semantics.pipeline import PipelineRun
from return_semantics.schemas import ValidatedClassification

COMPLETED_SEGMENT_STATUSES = frozenset({"completed", "completed_with_errors"})
TASK_ERROR_TEXT_LIMIT = 2000
TASK_EVENT_ERROR_TEXT_LIMIT = 500


@dataclass
class _SegmentRunContext:
    task_id: str
    segment_id: str
    task: dict[str, Any]
    segment: dict[str, Any]
    checkpoint_path: Path
    existing_results: dict[str, ValidatedClassification]
    base_model_calls: int
    base_cache_hits: int
    base_model_failures: int
    latest_run: PipelineRun | None = None

    def runtime_totals(self) -> tuple[int, int, int]:
        run = self.latest_run
        return (
            self.base_model_calls + (run.model_calls if run else 0),
            self.base_cache_hits + (run.cache_hits if run else 0),
            self.base_model_failures + (run.model_failures if run else 0),
        )
