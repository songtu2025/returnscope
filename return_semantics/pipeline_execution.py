from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from typing import TYPE_CHECKING

import pandas as pd

from return_semantics.pipeline_models import PipelineRun
from return_semantics.schemas import ValidatedClassification

if TYPE_CHECKING:
    from return_semantics.pipeline import _CommentClassifier


def _classify_selected_comments(
    selected: pd.DataFrame,
    classifier: _CommentClassifier,
    max_workers: int,
    progress: Callable[[int, int], None] | None,
    checkpoint: Callable[[PipelineRun], None] | None,
) -> PipelineRun:
    total = len(selected)
    rows = list(selected.itertuples(index=False))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(classifier.classify, row) for row in rows]
        for position, future in enumerate(as_completed(futures), start=1):
            classification_key, validated = future.result()
            classifier.tracker.add_result(classification_key, validated)
            if progress is not None:
                progress(position, total)
            if checkpoint is not None and (
                position == 1 or position == total or position % 5 == 0
            ):
                checkpoint(classifier.tracker.snapshot())
    run = classifier.tracker.snapshot()
    ordered_results: dict[str, ValidatedClassification] = {
        str(row.classification_key): run.classifications[str(row.classification_key)]
        for row in rows
        if str(row.classification_key) in run.classifications
    }
    return replace(run, classifications=ordered_results)
