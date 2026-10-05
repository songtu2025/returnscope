from __future__ import annotations

from typing import Any

from web_backend.dashboard_service import TEXT_ENCODING_ANOMALY


def _has_text_anomaly(*values: Any) -> bool:
    text = " ".join(str(value or "") for value in values)
    return bool(TEXT_ENCODING_ANOMALY.search(text))


def _filter_text_opinions(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        opinion
        for opinion in context.get("opinions", [])
        if not _has_text_anomaly(opinion.get("opinion"), opinion.get("evidence"))
    ]


def _filter_text_samples(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        sample
        for sample in context.get("samples", [])
        if not _has_text_anomaly(sample.get("comment"), sample.get("reason"))
    ]


def _filter_diagnostic_text(diagnostic: dict[str, Any]) -> dict[str, Any]:
    semantic_profile = diagnostic.get("semantic_profile", {})
    opinions = _filter_text_opinions(semantic_profile)
    samples = _filter_text_samples(diagnostic)
    return {
        **diagnostic,
        "semantic_profile": {**semantic_profile, "opinions": opinions},
        "samples": samples,
        "text_evidence": {
            "status": "available" if opinions or samples else "limited",
            "opinion_count": len(opinions),
            "sample_count": len(samples),
        },
    }


def _filter_issue_case_text(case: dict[str, Any]) -> dict[str, Any]:
    semantic_profile = case.get("semantic_profile", {})
    opinions = _filter_text_opinions(semantic_profile)
    samples = _filter_text_samples(case)
    return {
        **case,
        "semantic_profile": {**semantic_profile, "opinions": opinions},
        "samples": samples,
    }


def _filter_business_issue_text(issue: dict[str, Any]) -> dict[str, Any]:
    contexts = issue.get("contexts", {})
    opinions = _filter_text_opinions(contexts)
    samples = _filter_text_samples(contexts)
    return {**issue, "contexts": {**contexts, "opinions": opinions, "samples": samples}}
