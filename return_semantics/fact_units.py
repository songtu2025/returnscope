from __future__ import annotations

from return_semantics.schemas import ExtractedFact, SemanticUnit


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
