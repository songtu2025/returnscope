from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from return_semantics.schema_vocabulary import (
    DimensionScopeField,
    SentimentCode,
    StrictModel,
)


class LabelExample(StrictModel):
    text: str = Field(min_length=1, max_length=1000)
    applies: bool
    sentiment: SentimentCode | None = None
    explanation: str = Field(min_length=1, max_length=500)


class LabelDefinition(StrictModel):
    code: str
    name: str
    group: str = ""
    parent_code: str | None = None
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list, max_length=10)
    examples: list[LabelExample] = Field(default_factory=list, max_length=10)
    allowed_sentiments: list[SentimentCode]
    allowed_claim_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_examples(self) -> "LabelDefinition":
        for example in self.examples:
            if example.applies and example.sentiment not in self.allowed_sentiments:
                raise ValueError("适用示例必须选择该标签允许的评价方向")
            if not example.applies and example.sentiment is not None:
                raise ValueError("不适用示例不指定评价方向")
        return self


class EvidenceRequirement(StrictModel):
    semantic_requirement: str = ""
    label_code: str = Field(min_length=1)
    cues: list[str] = Field(min_length=1)
    unknown_opinion: str = Field(min_length=1)
    unknown_reason: str = Field(min_length=1)


class ImplicitEvidenceRule(StrictModel):
    semantic_requirement: str = ""
    label_code: str = Field(min_length=1)
    cues: list[str] = Field(min_length=1)


class ClaimEvidenceRequirement(StrictModel):
    semantic_requirement: str = ""
    label_code: str = Field(min_length=1)
    claim_id: str = Field(min_length=1)
    cues: list[str] = Field(min_length=1)


class DimensionContract(StrictModel):
    parent_code: str = Field(min_length=1)
    verdict_label_codes: list[str] = Field(min_length=1)
    scope_fields: list[DimensionScopeField] = Field(min_length=1)


class TaxonomyValidationRules(StrictModel):
    allowed_groups: list[str] = Field(default_factory=list)
    neutral_reason_labels: list[str] | None = None
    required_review_labels: list[str] = Field(default_factory=list)
    boundary_required_labels: list[str] = Field(default_factory=list)
    fallback_label_codes: list[str] = Field(default_factory=list)
    conflict_scope: Literal["comment", "evidence"] = "comment"
    opposite_reason_labels: dict[str, list[str]] = Field(default_factory=dict)
    conflicting_label_sets: list[list[str]] = Field(default_factory=list)
    evidence_requirements: list[EvidenceRequirement] = Field(default_factory=list)
    implicit_evidence_rules: list[ImplicitEvidenceRule] = Field(default_factory=list)
    claim_evidence_requirements: list[ClaimEvidenceRequirement] = Field(
        default_factory=list
    )
    dimension_contracts: list[DimensionContract] = Field(default_factory=list)


class CategoryDefinition(StrictModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    parent_code: str | None = None


class TaxonomyConfig(StrictModel):
    version: str
    structure_version: Literal[1, 2] = 1
    categories: list[CategoryDefinition] = Field(default_factory=list)
    recognition_profile: Literal[
        "legacy_v3", "keyword_free_v1", "semantic_v1", "fact_v2"
    ] = "legacy_v3"
    agent_family: str
    product_context: str
    allowed_parts: list[str] = Field(default_factory=lambda: ["UNSPECIFIED"])
    instructions: list[str] = Field(default_factory=list)
    validation_rules: TaxonomyValidationRules = Field(
        default_factory=TaxonomyValidationRules
    )
    labels: list[LabelDefinition]

    @model_validator(mode="after")
    def validate_rule_labels(self) -> "TaxonomyConfig":
        # 校验顺序决定多个错误并存时的第一条提示，拆分后仍保持原顺序。
        self._validate_label_structure()
        label_codes = {label.code for label in self.labels}
        self._validate_rule_references(label_codes)
        self._validate_dimension_contracts(label_codes)
        if any(
            len(set(codes)) < 2
            for codes in self.validation_rules.conflicting_label_sets
        ):
            raise ValueError("冲突标签组至少需要两个不同标签")
        return self

    def _validate_label_structure(self) -> None:
        if self.structure_version == 2:
            from return_semantics.taxonomy_hierarchy import validate_hierarchy

            validate_hierarchy(self)
        elif self.categories or any(label.parent_code for label in self.labels):
            raise ValueError("层级标签必须使用 structure_version=2")
        groups = self.validation_rules.allowed_groups
        if (
            self.structure_version == 1
            and groups
            and any(label.group not in groups for label in self.labels)
        ):
            raise ValueError("标签分组必须来自标准规定的业务分组")

    def _validate_rule_references(self, label_codes: set[str]) -> None:
        rule_codes = {
            code
            for codes in self.validation_rules.opposite_reason_labels.values()
            for code in codes
        }
        rule_codes.update(
            code
            for codes in self.validation_rules.conflicting_label_sets
            for code in codes
        )
        rule_codes.update(
            rule.label_code for rule in self.validation_rules.evidence_requirements
        )
        rule_codes.update(
            rule.label_code for rule in self.validation_rules.implicit_evidence_rules
        )
        rule_codes.update(
            rule.label_code
            for rule in self.validation_rules.claim_evidence_requirements
        )
        rule_codes.update(self.validation_rules.neutral_reason_labels or [])
        rule_codes.update(self.validation_rules.required_review_labels)
        rule_codes.update(self.validation_rules.boundary_required_labels)
        rule_codes.update(self.validation_rules.fallback_label_codes)
        unknown_codes = sorted(rule_codes.difference(label_codes))
        if unknown_codes:
            raise ValueError(f"校验规则引用了未知标签: {unknown_codes}")

    def _validate_dimension_contracts(self, label_codes: set[str]) -> None:
        from return_semantics.taxonomy_hierarchy import label_path_codes

        contracts = self.validation_rules.dimension_contracts
        decision_parent_codes = [contract.parent_code for contract in contracts]
        category_codes = {category.code for category in self.categories}
        if decision_parent_codes and self.structure_version != 2:
            raise ValueError("维度裁决契约仅适用于层级标签")
        unknown_parent_codes = sorted(set(decision_parent_codes) - category_codes)
        if unknown_parent_codes:
            raise ValueError(f"维度裁决契约引用了未知分类: {unknown_parent_codes}")
        if len(decision_parent_codes) != len(set(decision_parent_codes)):
            raise ValueError("同一分类只能配置一条维度裁决契约")
        for contract in contracts:
            self._validate_dimension_contract(contract, label_codes)
        for label in self.labels:
            matching_contracts = [
                contract.parent_code
                for contract in contracts
                if contract.parent_code in label_path_codes(self, label.code)[:-1]
            ]
            if len(matching_contracts) > 1:
                raise ValueError(f"维度裁决契约不能重叠管理同一标签: {label.code}")

    def _validate_dimension_contract(
        self, contract: DimensionContract, label_codes: set[str]
    ) -> None:
        from return_semantics.taxonomy_hierarchy import label_path_codes

        if len(contract.verdict_label_codes) != len(set(contract.verdict_label_codes)):
            raise ValueError("维度裁决契约的结论标签不能重复")
        if len(contract.scope_fields) != len(set(contract.scope_fields)):
            raise ValueError("维度裁决契约的作用域字段不能重复")
        invalid_verdicts = [
            code for code in contract.verdict_label_codes if code not in label_codes
        ]
        if invalid_verdicts:
            raise ValueError(f"维度裁决契约引用了未知标签: {invalid_verdicts}")
        outside_parent = [
            code
            for code in contract.verdict_label_codes
            if contract.parent_code not in label_path_codes(self, code)[:-1]
        ]
        if outside_parent:
            raise ValueError(f"维度结论标签不属于配置父级: {outside_parent}")


# 保留原模块标识，兼容既有模型序列化和导入入口。
for _schema_type in (
    LabelExample,
    LabelDefinition,
    EvidenceRequirement,
    ImplicitEvidenceRule,
    ClaimEvidenceRequirement,
    DimensionContract,
    TaxonomyValidationRules,
    CategoryDefinition,
    TaxonomyConfig,
):
    _schema_type.__module__ = "return_semantics.schemas"
del _schema_type
