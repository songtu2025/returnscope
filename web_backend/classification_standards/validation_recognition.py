from __future__ import annotations

from copy import deepcopy
from typing import Any

from return_semantics.prompt import prompt_version, recognition_fingerprint
from return_semantics.schemas import TaxonomyConfig
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.classification_validation_quality import FACT_QUALITY_POLICY


class ClassificationStandardValidationRecognitionMixin:
    standard_service: ClassificationStandardService

    def _apply_recognition_context(
        self,
        source: dict[str, Any],
        draft: dict[str, Any],
        draft_id: str,
        expected_revision: int,
        comparison_type: str,
    ) -> None:
        candidate = TaxonomyConfig.model_validate(draft["snapshot"]["taxonomy"])
        baseline = self.standard_service.taxonomy_for_version(
            str(draft["base_version_id"])
        )
        if comparison_type != "standard_version":
            candidate = candidate.model_copy(
                update={
                    "version": f"draft-{draft_id}-r{expected_revision}",
                }
            )
            baseline = candidate.model_copy(
                update={
                    "recognition_profile": "legacy_v3"
                    if comparison_type == "keyword_ab"
                    else "keyword_free_v1",
                }
            )
            candidate = candidate.model_copy(
                update={
                    "recognition_profile": "keyword_free_v1"
                    if comparison_type == "keyword_ab"
                    else "semantic_v1",
                }
            )
        source["comparison_type"] = comparison_type
        source["recognition_contract"] = {
            side: {
                "profile": config.recognition_profile,
                "prompt_version": prompt_version(config),
                "fingerprint": recognition_fingerprint(config),
            }
            for side, config in (("baseline", baseline), ("candidate", candidate))
        }
        source["recognition_taxonomies"] = {
            "baseline": baseline.model_dump(mode="json"),
            "candidate": candidate.model_dump(mode="json"),
        }
        source["result"].update(
            {
                "comparison_type": comparison_type,
                "recognition_contract": source["recognition_contract"],
            }
        )
        if comparison_type != "standard_version":
            source["result"]["comparison_mode"] = "baseline_and_draft"
        if candidate.recognition_profile == "fact_v2":
            source["quality_policy"] = deepcopy(FACT_QUALITY_POLICY)
            source["result"]["quality_policy"] = source["quality_policy"]
