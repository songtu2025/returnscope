from __future__ import annotations

from return_semantics.fact_mapping_models import EvidenceLabelAdjudication
from return_semantics.schemas import (
    ExtractedFact,
    FactMapping,
    FactRelationType,
    LabelDefinition,
    SemanticDisposition,
)


def _accepted_label_code(
    mapping: FactMapping,
    item: EvidenceLabelAdjudication,
    current_code: str | None,
) -> str:
    if current_code is None or item.label_code != current_code:
        raise ValueError("ACCEPT只能接受该事实当前已有的唯一候选标签")
    if mapping.evidence_relation == "INFERRED":
        raise ValueError("非等价推导不能使用ACCEPT")
    return current_code


def _replacement_label_code(
    item: EvidenceLabelAdjudication,
    current_code: str | None,
    allowed: dict[str, list[str]],
) -> str:
    if item.label_code is None or item.label_code not in allowed[item.fact_id]:
        raise ValueError("REPLACE只能选择该事实允许的一个标签")
    if item.label_code == current_code:
        raise ValueError("候选标签未改变时应使用ACCEPT")
    return item.label_code


def _normalized_adjudication_fields(
    item: EvidenceLabelAdjudication,
    current_code: str | None,
    allowed_codes: list[str],
) -> tuple[str, str | None, str]:
    action, label_code = item.action, item.label_code
    if action == "ACCEPT" and label_code is None and current_code is not None:
        return action, current_code, "ACCEPT缺少标签，已补当前唯一候选"
    if action == "REPLACE" and current_code is not None and label_code == current_code:
        return "ACCEPT", label_code, "REPLACE选择当前唯一候选，已归一为ACCEPT"
    if (
        action == "ACCEPT"
        and current_code is None
        and label_code is not None
        and label_code in allowed_codes
    ):
        return "REPLACE", label_code, "空映射的ACCEPT携带唯一标签，已归一为REPLACE"
    if action in {"ABSTAIN", "REVIEW"} and label_code is not None:
        return action, None, f"{action}不应携带标签，已清空"
    return action, label_code, ""


def _adjudication_selection(
    mapping: FactMapping,
    item: EvidenceLabelAdjudication,
    allowed: dict[str, list[str]],
) -> tuple[str | None, SemanticDisposition | None, list[str]]:
    current_codes = mapping.label_codes or mapping.candidate_label_codes
    current_code = current_codes[0] if current_codes else None
    if item.action == "ACCEPT":
        selected_code = _accepted_label_code(mapping, item, current_code)
        disposition = None
    elif item.action == "REPLACE":
        selected_code = _replacement_label_code(item, current_code, allowed)
        disposition = None
    else:
        if item.label_code is not None:
            raise ValueError("ABSTAIN和REVIEW不能携带标签")
        selected_code = None
        disposition = (
            SemanticDisposition.EXPECTED_ABSTENTION
            if item.action == "ABSTAIN"
            else SemanticDisposition.MAPPING_UNCERTAIN
        )
    return selected_code, disposition, current_codes


def _adjudicated_mapping(
    mapping: FactMapping,
    item: EvidenceLabelAdjudication,
    *,
    fact: ExtractedFact,
    labels_by_code: dict[str, LabelDefinition],
    allowed: dict[str, list[str]],
    fallback_codes: set[str],
) -> FactMapping:
    selected_code, disposition, current_codes = _adjudication_selection(
        mapping, item, allowed
    )
    if selected_code is not None:
        _validated_mapping_label(fact, selected_code, labels_by_code, allowed)
    return FactMapping.model_validate(
        {
            **mapping.model_dump(mode="json"),
            "label_codes": [selected_code] if selected_code else [],
            "candidate_label_codes": [] if selected_code else current_codes,
            "disposition": disposition,
            "reason": item.reason,
            "relation_type": FactRelationType.NONE,
            "related_fact_ids": [],
            "evidence_relation": (
                mapping.evidence_relation if item.action == "ACCEPT" else "DIRECT"
            ),
            "adjudication_action": item.action,
            "fallback_is_independent": (
                mapping.fallback_is_independent
                if selected_code in fallback_codes
                else False
            ),
        }
    )


def _normalized_adjudication(
    mapping: FactMapping,
    item: EvidenceLabelAdjudication,
    *,
    allowed_codes: list[str],
) -> tuple[EvidenceLabelAdjudication, bool]:
    """只修复能由当前唯一候选或动作中唯一标签确定的格式错误。"""
    current_codes = mapping.label_codes or mapping.candidate_label_codes
    current_code = current_codes[0] if current_codes else None
    action, label_code, recovery = _normalized_adjudication_fields(
        item, current_code, allowed_codes
    )
    if not recovery:
        return item, False
    reason = f"{item.reason}；裁决格式已归一：{recovery}"
    return item.model_copy(
        update={"action": action, "label_code": label_code, "reason": reason}
    ), True


def _validated_mapping_label(
    fact: ExtractedFact,
    code: str,
    labels: dict[str, LabelDefinition],
    allowed: dict[str, list[str]],
) -> LabelDefinition:
    if code not in allowed[fact.fact_id] or code not in labels:
        raise ValueError(f"事实映射使用分支外或不存在的标签: {code}")
    label = labels[code]
    if fact.sentiment not in label.allowed_sentiments:
        raise ValueError(f"事实方向不符合标签允许方向: {code}")
    return label
