"""人工复核后的标签汇总与事实映射投影。"""

from typing import Any


def project_review_labels(
    units: list[dict[str, Any]],
    previous_problem_codes: list[str],
    previous_label: str,
    selected: str,
) -> tuple[list[str], list[str], list[str]]:
    neutral_problem_codes = set(previous_problem_codes)
    if previous_label in neutral_problem_codes:
        neutral_problem_codes.remove(previous_label)
        neutral_problem_codes.add(selected)
    problem_codes: list[str] = []
    positive_codes: list[str] = []
    negative_codes: list[str] = []
    for unit in units:
        code = str(unit.get("label_code", ""))
        sentiment = str(unit.get("sentiment", ""))
        if sentiment == "POSITIVE":
            positive_codes.append(code)
        elif sentiment == "NEGATIVE":
            problem_codes.append(code)
            negative_codes.append(code)
        elif code in neutral_problem_codes:
            problem_codes.append(code)
    return (
        list(dict.fromkeys(problem_codes)),
        list(dict.fromkeys(positive_codes)),
        list(dict.fromkeys(negative_codes)),
    )


def project_review_facts(
    classification: dict[str, Any],
    reviews: dict[str, dict[str, Any]],
    handled: set[str],
) -> None:
    """仅更新已处置事实的映射，保留其他事实及其顺序。"""
    removed = {
        item_id.removeprefix("fact:")
        for item_id, review in reviews.items()
        if review["action"] == "remove" and item_id in handled
    }
    classification["extracted_facts"] = [
        fact
        for fact in classification.get("extracted_facts", [])
        if fact["fact_id"] not in removed
    ]
    mappings = [
        mapping
        for mapping in classification.get("fact_mappings", [])
        if mapping["fact_id"] not in removed
    ]
    for mapping in mappings:
        review = reviews.get(f"fact:{mapping['fact_id']}")
        if review is None or not review.get("applied"):
            continue
        code = review.get("label_code") if review["action"] == "change_label" else None
        mapping.update(
            label_codes=[code] if code else [],
            candidate_label_codes=[],
            disposition=None if code else "EXPECTED_ABSTENTION",
            adjudication_action="REPLACE" if code else "ABSTAIN",
            reason=review.get("note") or "人工逐项复核",
        )
    classification["fact_mappings"] = mappings
