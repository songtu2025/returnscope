from __future__ import annotations

from return_semantics.schemas import (
    ClaimRelation,
    SemanticUnit,
    UnknownSemantic,
)

MATERIAL_QUALITY_CUES = (
    "cheap",
    "poor quality",
    "low quality",
    "flimsy",
    "thin material",
    "bad quality",
    "bad material",
    "not good quality",
    "inferior",
)
PROTECTION_CUES = (
    "rock",
    "stone",
    "pebble",
    "gravel",
    "shell",
    "sharp",
    "hot sand",
    "protect",
    "feel things",
    "felt things",
    "hurt",
    "pain",
)
SMALLER_SIZE_CUES = (
    "need smaller",
    "needed smaller",
    "need a smaller",
    "wanted smaller",
    "size down",
)
BIGGER_SIZE_CUES = (
    "need bigger",
    "needed bigger",
    "need a bigger",
    "wanted bigger",
    "size up",
)


def normalize_semantic_unit(
    unit: SemanticUnit,
) -> tuple[SemanticUnit | None, UnknownSemantic | None]:
    evidence = unit.evidence.lower()

    if unit.label_code == "QUALITY_CHEAP_MATERIAL" and not any(
        cue in evidence for cue in MATERIAL_QUALITY_CUES
    ):
        return None, UnknownSemantic(
            opinion="不喜欢材料，但没有说明具体问题",
            evidence=unit.evidence,
            reason="证据不足以判断材料廉价或质量差",
        )

    if unit.label_code == "FIT_TOO_LARGE" and any(
        cue in evidence for cue in SMALLER_SIZE_CUES
    ):
        unit = unit.model_copy(update={"implicit": True})
    if unit.label_code == "FIT_TOO_SMALL" and any(
        cue in evidence for cue in BIGGER_SIZE_CUES
    ):
        unit = unit.model_copy(update={"implicit": True})

    if (
        unit.label_code == "EXPERIENCE_THIN"
        and unit.claim_id == "CLM_PROTECT_01"
        and not any(cue in evidence for cue in PROTECTION_CUES)
    ):
        unit = unit.model_copy(
            update={
                "claim_relation": ClaimRelation.NONE,
                "claim_id": None,
            }
        )

    return unit, None
