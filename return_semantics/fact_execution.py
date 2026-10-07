from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from return_semantics.fact_extraction import (
    FactPipelineCancelled,
    _normalize_fact_branch_codes,
    _restore_evidence_spans,
    _validate_facts,
)
from return_semantics.fact_mapping import _mapping_payload
from return_semantics.schemas import (
    ExtractedFact,
    FactExtraction,
    FactExtractionSource,
    TaxonomyConfig,
)


@dataclass(frozen=True, kw_only=True)
class _FactExecutionContext:
    comment: str
    taxonomy: TaxonomyConfig
    call: Callable
    metrics: dict[str, int]


class _ModelCallAccumulator:
    def __init__(
        self,
        generate: Callable,
        *,
        model_name: str,
        reasoning_effort: str,
        should_cancel: Callable[[], bool] | None,
    ) -> None:
        self.generate = generate
        self.model_name = model_name
        self.reasoning_effort = reasoning_effort
        self.should_cancel = should_cancel
        self.usage: dict[str, int] = {}
        self.metrics: dict[str, int] = {}
        self.calls = 0

    def __call__(self, messages: list[dict[str, str]]) -> dict:
        if self.should_cancel is not None and self.should_cancel():
            raise FactPipelineCancelled("事实识别已取消")
        response = self.generate(
            messages,
            model=self.model_name,
            reasoning_effort=self.reasoning_effort,
        )
        self.calls += 1
        for target, values in (
            (self.usage, response.usage),
            (self.metrics, response.metrics),
        ):
            for key, value in values.items():
                target[key] = target.get(key, 0) + value
        return response.payload


def _extract_primary_facts(
    payload: dict,
    *,
    taxonomy: TaxonomyConfig,
    comment: str,
) -> list[ExtractedFact]:
    normalized = dict(payload)
    if isinstance(normalized.get("facts"), list):
        normalized["facts"] = [
            {
                **item,
                "extraction_source": FactExtractionSource.PRIMARY,
            }
            if isinstance(item, dict)
            else item
            for item in normalized["facts"]
        ]
    facts = _normalize_fact_branch_codes(
        FactExtraction.model_validate(normalized).facts,
        taxonomy,
    )
    facts = _restore_evidence_spans(facts, comment)
    _validate_facts(facts, comment, taxonomy)
    _mapping_payload(facts, taxonomy)
    return facts


def _validated_stage(
    messages: list[dict[str, str]],
    call: Callable,
    validate: Callable,
    recover: Callable | None = None,
):
    """只修复失败阶段一次，不重新支付已通过阶段的模型调用。"""
    try:
        return validate(call(messages))
    except ValueError as exc:
        correction = {
            "role": "user",
            "content": f"上次输出未通过校验：{exc}。请修复并重发完整JSON，不改写输入事实。",
        }
        repaired = call([*messages, correction])
        try:
            return validate(repaired)
        except ValueError:
            if recover is None:
                raise
            return recover(repaired)
