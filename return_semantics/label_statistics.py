from __future__ import annotations

from collections import Counter
from typing import Any

from return_semantics.data import ReturnDataset
from return_semantics.schemas import TaxonomyConfig, ValidatedClassification


def weighted_label_counts(
    dataset: ReturnDataset,
    results: dict[str, ValidatedClassification],
) -> tuple[Counter[str], Counter[str], Counter[str]]:
    problem_counts: Counter[str] = Counter()
    positive_counts: Counter[str] = Counter()
    primary_counts: Counter[str] = Counter()
    record_counts = dataset.records["classification_key"].value_counts()
    for key, result in results.items():
        weight = int(record_counts.get(key, 0))
        problem_counts.update({code: weight for code in result.problem_label_codes})
        positive_counts.update({code: weight for code in result.positive_label_codes})
        primary_counts.update({code: weight for code in result.primary_label_codes})
    return problem_counts, positive_counts, primary_counts


def top_problem_labels(
    dataset: ReturnDataset,
    results: dict[str, ValidatedClassification],
    taxonomy: TaxonomyConfig,
) -> list[dict[str, Any]]:
    labels = {label.code: label for label in taxonomy.labels}
    problem_counts, _, _ = weighted_label_counts(dataset, results)
    denominator = max(int(dataset.records["has_text_evidence"].sum()), 1)
    return [
        {
            "code": code,
            "name": labels[code].name,
            "group": labels[code].group,
            "count": count,
            "share": round(count / denominator * 100, 2),
        }
        for code, count in problem_counts.most_common(8)
        if code in labels
    ]
