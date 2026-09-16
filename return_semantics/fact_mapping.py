from __future__ import annotations

from typing import Literal

from pydantic import Field

from return_semantics.fact_extraction import (
    _allowed_labels_by_fact,
    _messages,
)
from return_semantics.fact_relations import can_form_terminal_label
from return_semantics.schemas import (
    DimensionContract,
    DimensionDecision,
    ExtractedFact,
    FactMapping,
    FactRelationType,
    LabelDefinition,
    ModelClassification,
    SemanticDisposition,
    SemanticUnit,
    StrictModel,
    TaxonomyConfig,
)
from return_semantics.taxonomy_hierarchy import label_path, label_path_codes


class FactMappings(StrictModel):
    mappings: list[FactMapping]


class ModelFactMapping(StrictModel):
    """模型只可填写语义映射字段，程序审计字段由编译阶段维护。"""

    fact_id: str = Field(min_length=1)
    label_codes: list[str] = Field(default_factory=list, max_length=1)
    reason: str = ""
    disposition: SemanticDisposition | None = None
    relation_type: FactRelationType = FactRelationType.NONE
    related_fact_ids: list[str] = Field(default_factory=list)
    evidence_relation: Literal["DIRECT", "EQUIVALENT", "INFERRED"] = "DIRECT"
    fallback_is_independent: bool = False


class ModelFactMappings(StrictModel):
    mappings: list[ModelFactMapping]


class EvidenceLabelAdjudication(StrictModel):
    fact_id: str
    action: Literal["ACCEPT", "REPLACE", "ABSTAIN", "REVIEW"]
    label_code: str | None = None
    reason: str


class EvidenceLabelAdjudications(StrictModel):
    adjudications: list[EvidenceLabelAdjudication]


def _mapping_can_form_terminal(fact: ExtractedFact, mapping: FactMapping) -> bool:
    adjudicated = mapping.adjudication_action in {"ACCEPT", "REPLACE"}
    return can_form_terminal_label(
        fact,
        allow_ambiguous_experiencer=adjudicated,
        allow_evidence=adjudicated,
    )


def _can_be_adjudicated(fact: ExtractedFact) -> bool:
    return can_form_terminal_label(
        fact,
        allow_ambiguous_experiencer=True,
        allow_evidence=True,
    )


def _validate_coverage(items: list, facts: list[ExtractedFact]) -> None:
    identifiers = [item.fact_id for item in items]
    if len(set(identifiers)) != len(identifiers) or set(identifiers) != {
        fact.fact_id for fact in facts
    }:
        raise ValueError("每个事实必须且只能有一条路由或映射记录")


def _mapping_payload(facts: list[ExtractedFact], taxonomy: TaxonomyConfig) -> dict:
    allowed = _allowed_labels_by_fact(facts, taxonomy)
    selected = {code for codes in allowed.values() for code in codes}
    return {
        "facts": [fact.model_dump(mode="json") for fact in facts],
        "allowed_labels_by_fact": allowed,
        "labels": [
            {**label.model_dump(mode="json"), "path": label_path(taxonomy, label.code)}
            for label in taxonomy.labels
            if label.code in selected
        ],
        "instructions": taxonomy.instructions,
        "dimension_contracts": [
            contract.model_dump(mode="json")
            for contract in taxonomy.validation_rules.dimension_contracts
        ],
        "fallback_label_codes": taxonomy.validation_rules.fallback_label_codes,
        "schema": ModelFactMappings.model_json_schema(),
    }


def _parse_model_fact_mappings(payload: dict) -> FactMappings:
    """忽略模型回传的程序审计字段，其余结构仍按严格契约校验。"""
    normalized = dict(payload)
    if isinstance(normalized.get("mappings"), list):
        normalized["mappings"] = [
            {
                key: value
                for key, value in item.items()
                if key not in {"candidate_label_codes", "adjudication_action"}
            }
            if isinstance(item, dict)
            else item
            for item in normalized["mappings"]
        ]
    writable = ModelFactMappings.model_validate(normalized)
    return FactMappings(
        mappings=[
            FactMapping.model_validate(mapping.model_dump(mode="json"))
            for mapping in writable.mappings
        ]
    )


def _adjudication_payload(
    classification: ModelClassification,
    taxonomy: TaxonomyConfig,
    comment: str,
    allowed: dict[str, list[str]],
) -> dict:
    candidate_facts = [
        fact
        for fact in classification.extracted_facts
        if _can_be_adjudicated(fact) and fact.product_ref.startswith("CURRENT")
    ]
    fact_ids = {fact.fact_id for fact in candidate_facts}
    label_codes = {code for fact_id in fact_ids for code in allowed.get(fact_id, [])}
    return {
        "comment": comment,
        "facts": [fact.model_dump(mode="json") for fact in candidate_facts],
        "current_mappings": [
            mapping.model_dump(mode="json")
            for mapping in classification.fact_mappings
            if mapping.fact_id in fact_ids
        ],
        "allowed_labels_by_fact": {
            fact_id: allowed.get(fact_id, []) for fact_id in fact_ids
        },
        "labels": [
            {**label.model_dump(mode="json"), "path": label_path(taxonomy, label.code)}
            for label in taxonomy.labels
            if label.code in label_codes
        ],
        "schema": EvidenceLabelAdjudications.model_json_schema(),
    }


def _adjudicated_mapping(
    mapping: FactMapping,
    item: EvidenceLabelAdjudication,
    *,
    fact: ExtractedFact,
    labels_by_code: dict[str, LabelDefinition],
    allowed: dict[str, list[str]],
    fallback_codes: set[str],
) -> FactMapping:
    current_codes = mapping.label_codes or mapping.candidate_label_codes
    current_code = current_codes[0] if current_codes else None
    if item.action == "ACCEPT":
        if current_code is None or item.label_code != current_code:
            raise ValueError("ACCEPT只能接受该事实当前已有的唯一候选标签")
        if mapping.evidence_relation == "INFERRED":
            raise ValueError("非等价推导不能使用ACCEPT")
        selected_code = current_code
        disposition = None
    elif item.action == "REPLACE":
        if item.label_code is None or item.label_code not in allowed[item.fact_id]:
            raise ValueError("REPLACE只能选择该事实允许的一个标签")
        if item.label_code == current_code:
            raise ValueError("候选标签未改变时应使用ACCEPT")
        selected_code = item.label_code
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
    action = item.action
    label_code = item.label_code
    recovery = ""
    if action == "ACCEPT" and label_code is None and current_code is not None:
        label_code = current_code
        recovery = "ACCEPT缺少标签，已补当前唯一候选"
    elif (
        action == "REPLACE" and current_code is not None and label_code == current_code
    ):
        action = "ACCEPT"
        recovery = "REPLACE选择当前唯一候选，已归一为ACCEPT"
    elif (
        action == "ACCEPT"
        and current_code is None
        and label_code is not None
        and label_code in allowed_codes
    ):
        action = "REPLACE"
        recovery = "空映射的ACCEPT携带唯一标签，已归一为REPLACE"
    elif action in {"ABSTAIN", "REVIEW"} and label_code is not None:
        label_code = None
        recovery = f"{action}不应携带标签，已清空"
    if not recovery:
        return item, False
    reason = f"{item.reason}；裁决格式已归一：{recovery}"
    return item.model_copy(
        update={"action": action, "label_code": label_code, "reason": reason}
    ), True


def _fact_identity(fact: ExtractedFact, code: str) -> tuple:
    return (
        fact.source_ref,
        fact.experiencer_ref,
        fact.actor_ref,
        fact.product_ref,
        fact.variant_ref,
        fact.event_ref,
        fact.reference_basis,
        fact.subject,
        fact.part,
        code,
        fact.sentiment,
        fact.statement_type,
        fact.fact_role,
        fact.causal_attribution,
        fact.operation,
        fact.condition,
    )


def _retain_fact_unit(
    units: list[SemanticUnit],
    seen: dict[tuple, int],
    identity: tuple,
    unit: SemanticUnit,
    comment: str,
) -> None:
    if identity not in seen:
        for previous_identity, index in seen.items():
            if _overlapping_fact_identity(
                previous_identity, identity, units[index], unit
            ):
                seen[identity] = index
                break
    if identity not in seen:
        seen[identity] = len(units)
        units.append(unit)
    elif units[seen[identity]].assertion == unit.assertion:
        previous = units[seen[identity]]
        previous.fact_ids = list(dict.fromkeys([*previous.fact_ids, *unit.fact_ids]))
        if unit.opinion not in previous.opinion.split("；"):
            previous.opinion = f"{previous.opinion}；{unit.opinion}"
        start = min(comment.index(previous.evidence), comment.index(unit.evidence))
        end = max(
            comment.index(previous.evidence) + len(previous.evidence),
            comment.index(unit.evidence) + len(unit.evidence),
        )
        previous.evidence = comment[start:end]


def _overlapping_fact_identity(
    previous: tuple,
    current: tuple,
    previous_unit: SemanticUnit,
    unit: SemanticUnit,
) -> bool:
    """仅对相同证据的非空完整条件项严格包含关系放宽合并。"""
    if previous[:-1] != current[:-1] or previous_unit.assertion != unit.assertion:
        return False
    if previous_unit.evidence.strip() != unit.evidence.strip():
        return False
    conditions = [
        {part.strip() for part in value.replace("；", ";").split(";") if part.strip()}
        for value in (previous[-1], current[-1])
    ]
    left, right = conditions
    return bool(left and right) and (left < right or right < left)


def _adjudication_messages(payload: dict) -> list[dict[str, str]]:
    return _messages(
        "独立核验每个当前商品、具体、已确认且非正常弃权类型的CONCLUSION或EVIDENCE事实，"
        "输出schema规定JSON；每个fact_id必须恰好一个最终动作，CONTEXT不参与终态裁决。"
        "不得改写或补充事实。ACCEPT只能保留当前已有候选，并在label_code原样填写该候选；"
        "current_mappings中的candidate_label_codes只记录初始模型候选，ACCEPT应承接其中的唯一候选；"
        "REPLACE可纠正遗漏或错误粒度，但只能从allowed_labels_by_fact中选择一个更准确标签。"
        "只有证据直接或逻辑等价蕴含最终标签定义，确定性充分，且体验者、商品、事件、部位和使用场景作用域一致时ACCEPT或REPLACE。"
        "EVIDENCE只有在原文自身已经完整表达可独立聚合的属性、表现或业务结论时才可ACCEPT或REPLACE；"
        "仅用于解释其他结论的现象、条件、原因或局部支持片段必须ABSTAIN，不能因相关就晋升终态。"
        "同一作用域、同一评价维度已有准确性、速度、稳定性或限制CONCLUSION时，基础能力EVIDENCE必须ABSTAIN，"
        "不得与该CONCLUSION重复保留同一标签。商品细节、结构或描述差异不得在原文未明示商品身份、规格或颜色错误时裁决为发错商品。"
        "商品页展示的结构、加固或细节在实物中缺失，不等于缝制、装配、收边或制作工艺差；"
        "没有明确工艺评价或具体失效时必须ABSTAIN，不得裁决为做工或质量标签。"
        "证据明确不蕴含候选标签时ABSTAIN，包括非等价属性推导、仅凭常识关联、客观设计未经过实际验证、"
        "低确定性表达、商品宣称、外观推测、预测、未测试、笼统总体评价，或已被具体事实覆盖且不新增业务信息。"
        "只有证据本身确有两种合理解释、标签定义边界含糊，或作用域歧义会改变标签真值或业务作用域时才REVIEW；"
        "直接陈述的商品固有结构、材质或客观能力可以在商品作用域下ACCEPT或REPLACE，"
        "不能仅因人物指代不明确而REVIEW；合身、舒适及其他依赖具体体验者的主观感受在体验者无法唯一确定时仍须REVIEW。"
        "ABSTAIN和REVIEW的label_code必须为空。"
        "不能把明确不支持标签的候选送人工复核，也不能因初始映射为空就遗漏可由允许标签准确表达的事实。"
        "连续语境已引入明确人物时，必须核验后续体验是否确有证据切换回评论者；没有唯一证据时REVIEW。"
        "reason用中文简述裁决依据，不得用reason改变结构化事实。",
        payload,
    )


def _mapping_messages(payload: dict) -> list[dict[str, str]]:
    return _messages(
        "仅将已抽取事实映射到该fact_id允许的末端标签，输出schema规定JSON。"
        "不得增删或改写事实。每个fact_id恰好一条记录；无合适标签时label_codes为空并写reason。"
        "无标签时必须填写disposition：正常忽略用EXPECTED_ABSTENTION，标签缺口用TAXONOMY_GAP，"
        "无法可靠选择用MAPPING_UNCERTAIN，其他商品或范围外事实用OUT_OF_SCOPE；"
        "仅作为维度裁决证据或上下文且不独立形成候选标签时用EVIDENCE_ONLY。"
        "映射成功时reason也必须用中文简洁说明该事实为什么符合所选标签边界。"
        "evidence_relation必须按逻辑支持关系填写：事实直接表达标签属性为DIRECT，"
        "与标签命题逻辑等价为EQUIVALENT，只能由相关性、常识或某一属性的缺失推出另一属性时为INFERRED。"
        "否定一个属性不自动证明另一个属性或其反义属性，除非标签定义明确将两者规定为等价命题。"
        "处置优先级固定：预测、假设、商品宣称、外观性能推测、未测试、建议、否认与未来购买意图先用EXPECTED_ABSTENTION；"
        "RECOMMENDATION表示当前购买态度，若允许标签能直接表达该态度，应正常映射；"
        "用户明确造成的商品状态也用EXPECTED_ABSTENTION，不能映射为商品固有缺陷；"
        "其余EVIDENCE或CONTEXT事实用EVIDENCE_ONLY；只有CONCLUSION未映射时才判断标签缺口或映射不确定。"
        "reason只用于解释，不参与系统规则判断。事实之间的关系必须使用relation_type和related_fact_ids表达："
        "COVERED_BY表示当前泛化结论已被关联的具体结论覆盖；SUPPORTS表示当前证据支持关联结论；"
        "QUALIFIES表示当前上下文限定关联结论；CAUSED_BY表示当前后果由关联结论造成；无关系用NONE。"
        "COVERED_BY和CAUSED_BY的来源角色为CONCLUSION，SUPPORTS来源为EVIDENCE，QUALIFIES来源为CONTEXT。"
        "非NONE关系必须引用同一核心作用域中的现有CONCLUSION事实，不能自引用或形成覆盖链；"
        "关系来源本身不映射标签，label_codes必须为空。"
        "如果事实明确是另一已识别具体问题的后果、条件、理由或泛化重述，必须使用上述关系或EVIDENCE_ONLY表达，"
        "且fallback_is_independent=false，不能再生成独立兜底标签。"
        "同一原子事实最多一个最具体标签，不并列泛化总结或后果标签。"
        "跨事实也检查标题、正文、因果后果及泛化总结是否重复；具体缺陷已有映射时不再并列泛化标签。"
        "购买多副或为多人购买不等于买多了；只有明确数量超出需要或误重复购买才属于买多了。"
        "fallback_label_codes中的标签仅承接没有更具体标签的明确评价或退货原因。"
        "只有该事实在去掉标题总结、重述、设计或客观描述后仍能独立成立，"
        "且未被任何具体事实或标签解释时，才可以选兜底标签并设fallback_is_independent=true；其他映射中保持false。"
        "同一事实或同一证据与作用域已有非兜底标签时，不得并列选择兜底标签。"
        "客观属性、尚未验证的预测、操作建议及已由具体事实覆盖的重复泛化不得使用兜底标签。"
        "严格保留原方向、对象、条件和建议程度；计划用途不能转成已实现功能。"
        "基础操作能够完成只证明功能可用，不等于性能达到正向水平；"
        "同一作用域、同一评价维度同时存在基础能力EVIDENCE与准确性、速度、稳定性或限制CONCLUSION时，"
        "只映射限制CONCLUSION；基础能力EVIDENCE必须label_codes为空、disposition=EVIDENCE_ONLY，"
        "并用SUPPORTS或QUALIFIES关联该CONCLUSION，禁止两个事实重复映射同一标签。"
        "引用商品页形成的不符事实应优先选择证据直接支持的最具体属性标签；没有更具体标签时才使用描述或预期不符类标签。"
        "只有原文明示收到错误的商品身份、规格或颜色时才选择发错商品类标签；商品细节、结构或描述差异不等于发错商品。"
        "商品页对比中仅缺少展示的结构、加固或细节时，若原文没有明确评价缝制、装配、收边、制作工艺好坏或具体失效，"
        "不得推断做工或质量问题；该客观差异只作为不符结论的证据，不独立映射质量标签。"
        "OTHER商品仅作对照，保留事实但不映射当前商品标签，也不当成本品覆盖缺口。"
        "客观状态不自动等于功能表现；需要事实包含该功能的相关使用或测试条件，不能从结果倒推未发生的机制。"
        "目录和品类规则只解释标签边界，不能创造评论事实。",
        payload,
    )


class FactDecisions(StrictModel):
    decisions: list[DimensionDecision]


def _contract_label_codes(
    taxonomy: TaxonomyConfig,
    contract: DimensionContract,
) -> set[str]:
    return {
        label.code
        for label in taxonomy.labels
        if contract.parent_code in label_path_codes(taxonomy, label.code)[:-1]
    }


def _decision_payload(
    facts: list[ExtractedFact],
    mappings: list[FactMapping],
    taxonomy: TaxonomyConfig,
) -> dict:
    labels = {label.code: label for label in taxonomy.labels}
    return {
        "facts": [fact.model_dump(mode="json") for fact in facts],
        "mappings": [mapping.model_dump(mode="json") for mapping in mappings],
        "contracts": [
            {
                **contract.model_dump(mode="json"),
                "verdict_labels": [
                    {
                        **labels[code].model_dump(mode="json"),
                        "path": label_path(taxonomy, code),
                    }
                    for code in contract.verdict_label_codes
                ],
            }
            for contract in taxonomy.validation_rules.dimension_contracts
        ],
        "instructions": taxonomy.instructions,
        "schema": FactDecisions.model_json_schema(),
    }


def _contract_branch_code(
    taxonomy: TaxonomyConfig,
    parent_code: str,
) -> str:
    parents = {category.code: category.parent_code for category in taxonomy.categories}
    current = parent_code
    while parents.get(current) is not None:
        current = str(parents[current])
    return current


def _validate_context_dimension(
    context_facts: list[ExtractedFact],
    contract: DimensionContract,
    taxonomy: TaxonomyConfig,
    mappings_by_id: dict[str, FactMapping],
) -> None:
    managed_codes = _contract_label_codes(taxonomy, contract)
    branch_code = _contract_branch_code(taxonomy, contract.parent_code)
    for fact in context_facts:
        mapping = mappings_by_id[fact.fact_id]
        candidate_codes = mapping.label_codes or mapping.candidate_label_codes
        if candidate_codes and any(
            code not in managed_codes for code in candidate_codes
        ):
            raise ValueError(f"维度上下文候选标签不属于配置父级: {fact.fact_id}")
        if not candidate_codes and branch_code not in fact.candidate_branch_codes:
            raise ValueError(f"维度上下文事实不属于配置父级分支: {fact.fact_id}")


def _record_downgraded_facts(
    decision: DimensionDecision,
    mappings_by_id: dict[str, FactMapping],
    reason: str,
    downgraded_fact_reasons: dict[str, str],
) -> None:
    for fact_id in decision.supporting_fact_ids:
        mapping = mappings_by_id.get(fact_id)
        if mapping is not None and mapping.label_codes:
            downgraded_fact_reasons[fact_id] = reason


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
