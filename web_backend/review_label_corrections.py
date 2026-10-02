from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any, cast

from return_semantics.comment_summary import compile_comment_semantics
from return_semantics.schemas import SemanticUnit, TaxonomyConfig, UnknownSemantic
from return_semantics.semantic_review import build_semantic_review_view


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


class _ReviewProjection:
    """只投影本次人工处置，不重新运行模型或全量语义规则。"""

    def __init__(
        self, classification: dict[str, Any], taxonomy: TaxonomyConfig, comment: str
    ) -> None:
        self.result = deepcopy(classification)
        self.taxonomy = taxonomy
        self.labels = {label.code: label for label in taxonomy.labels}
        view = build_semantic_review_view(classification, comment, taxonomy)
        self.items = {
            item["item_id"]: item
            for item in cast(list[dict[str, Any]], view["semantic_items"])
        }
        self.items.update(
            {
                f"unexplained-{index}": {
                    "opinion": fragment,
                    "evidence_text": fragment,
                }
                for index, fragment in enumerate(
                    cast(list[str], view["unexplained_fragments"])
                )
            }
        )
        self.reviews = {
            item["semantic_item_id"]: item
            for item in self.result.get("human_semantic_reviews", [])
            if not item.get("applied")
        }
        self.handled: set[str] = set()
        self.units: list[dict[str, Any]] = []
        self.unknowns: list[dict[str, Any]] = []
        self.problems: list[str] = []
        self.primary: list[str] = []

    @staticmethod
    def _item_id(item: dict[str, Any], field: str) -> str:
        view = build_semantic_review_view({field: [item]}, "")
        return cast(list[dict[str, Any]], view["semantic_items"])[0]["item_id"]

    def _sentiment(self, original: dict[str, Any], review: dict[str, Any]) -> str:
        allowed = [
            str(value) for value in self.labels[review["label_code"]].allowed_sentiments
        ]
        known = original.get("sentiment")
        chosen = review.get("sentiment")
        if known and chosen and chosen != known:
            raise ValueError("已有语义的评价方向必须沿用原结果")
        selected = known or chosen or (allowed[0] if len(allowed) == 1 else None)
        if not selected:
            raise ValueError("请为无法确定方向的观点选择评价方向")
        if selected not in allowed:
            raise ValueError("评价方向不符合所选标签的允许范围")
        return str(selected)

    def _unit(self, original: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
        fields = {
            key: value
            for key, value in original.items()
            if key in SemanticUnit.model_fields
        }
        if not fields.get("statement_type"):
            fields.pop("statement_type", None)
        return SemanticUnit.model_validate(
            {
                "subject": "PRODUCT",
                "assertion": "AFFIRMED",
                "part": "UNSPECIFIED",
                "implicit": False,
                **fields,
                "evidence": original.get("evidence") or original["evidence_text"],
                "label_code": review["label_code"],
                "sentiment": self._sentiment(original, review),
            }
        ).model_dump(mode="json")

    def _decide(self, original: dict[str, Any], item_id: str, field: str) -> None:
        review = self.reviews.get(item_id)
        if review is None:
            (self.units if field == "semantic_units" else self.unknowns).append(
                original
            )
            return
        self.handled.add(item_id)
        review["evidence_text"] = original.get("evidence") or original["evidence_text"]
        if review["action"] == "change_label":
            updated = self._unit(original, review)
            self.units.append(updated)
            if original.get("is_primary_reason"):
                self.primary.append(updated["label_code"])
            review["result_item_id"] = self._item_id(updated, "semantic_units")
        elif review["action"] == "no_tag_needed":
            updated = UnknownSemantic.model_validate(
                {
                    **{
                        key: value
                        for key, value in original.items()
                        if key in UnknownSemantic.model_fields
                    },
                    "evidence": original.get("evidence") or original["evidence_text"],
                    "reason": review.get("note") or "人工确认无需归类",
                    "disposition": "EXPECTED_ABSTENTION",
                }
            ).model_dump(mode="json")
            self.unknowns.append(updated)
            review["result_item_id"] = self._item_id(updated, "unknown_semantics")
        review["applied"] = True

    def _project_units(self) -> None:
        for unit in self.result.get("semantic_units", []):
            start = len(self.units)
            fact_ids = list(
                dict.fromkeys(
                    unit.get("fact_ids")
                    or ([unit["fact_id"]] if unit.get("fact_id") else [])
                )
            )
            selected = [
                fact_id for fact_id in fact_ids if f"fact:{fact_id}" in self.reviews
            ]
            if self._unchanged_reviewed_unit(unit, selected):
                self.units.append(unit)
            elif not selected:
                self._decide(
                    unit, self._item_id(unit, "semantic_units"), "semantic_units"
                )
            else:
                remaining = [fact_id for fact_id in fact_ids if fact_id not in selected]
                for fact_id in selected:
                    self._decide(
                        unit
                        if len(fact_ids) == 1
                        else {**unit, "fact_id": fact_id, "fact_ids": [fact_id]},
                        f"fact:{fact_id}",
                        "semantic_units",
                    )
                if remaining:
                    self.units.append(
                        {**unit, "fact_id": remaining[0], "fact_ids": remaining}
                    )
            codes = [item["label_code"] for item in self.units[start:]]
            if unit["label_code"] in self.result.get("problem_label_codes", []):
                self.problems.extend(codes)
            if unit["label_code"] in self.result.get("primary_label_codes", []):
                self.primary.extend(codes)

    def _unchanged_reviewed_unit(
        self, unit: dict[str, Any], selected: list[str]
    ) -> bool:
        reviews = [self.reviews[f"fact:{fact_id}"] for fact_id in selected]
        if not reviews or any(
            review["action"] != "change_label"
            or review["label_code"] != unit["label_code"]
            for review in reviews
        ):
            return False
        for fact_id, review in zip(selected, reviews, strict=True):
            self._sentiment(unit, review)
            self.handled.add(f"fact:{fact_id}")
            review.update(
                applied=True,
                result_item_id=f"fact:{fact_id}",
                evidence_text=unit["evidence"],
            )
        return True

    def _project_unknowns(self) -> None:
        facts = {
            fact["fact_id"]: fact for fact in self.result.get("extracted_facts", [])
        }
        for unknown in self.result.get("unknown_semantics", []):
            fact = facts.get(unknown.get("fact_id"), {})
            item_id = self._item_id(unknown, "unknown_semantics")
            if item_id in self.handled:
                continue
            original = {**fact, **unknown} if item_id in self.reviews else unknown
            self._decide(original, item_id, "unknown_semantics")
        for item_id in self.reviews:
            if item_id in self.handled:
                continue
            item = self.items.get(item_id)
            if item is not None:
                fact = facts.get(item.get("fact_id"), {})
                self._decide({**fact, **item}, item_id, "unknown_semantics")

    def _project_added(self) -> None:
        for index, added in enumerate(
            self.result.get("human_added_semantic_items", [])
        ):
            if added.get("applied"):
                continue
            # 纳入复核人、时间和序号，避免不同批次补录项编号重复。
            identity = repr(
                (
                    added.get("assessed_by"),
                    added.get("assessed_at"),
                    index,
                    added.get("item_id"),
                    added["evidence_text"],
                )
            )
            fact_id = "manual:" + hashlib.sha256(identity.encode()).hexdigest()[:16]
            unit = self._unit(
                {
                    **added,
                    "opinion": added.get("opinion") or added["evidence_text"],
                    "fact_id": fact_id,
                    "fact_ids": [fact_id],
                },
                added,
            )
            self.units.append(unit)
            added.update(applied=True, result_item_id=f"fact:{fact_id}")

    def _project_facts(self) -> None:
        removed = {
            item_id.removeprefix("fact:")
            for item_id, review in self.reviews.items()
            if review["action"] == "remove" and item_id in self.handled
        }
        self.result["extracted_facts"] = [
            fact
            for fact in self.result.get("extracted_facts", [])
            if fact["fact_id"] not in removed
        ]
        mappings = [
            mapping
            for mapping in self.result.get("fact_mappings", [])
            if mapping["fact_id"] not in removed
        ]
        for mapping in mappings:
            review = self.reviews.get(f"fact:{mapping['fact_id']}")
            if review is None or not review.get("applied"):
                continue
            code = (
                review.get("label_code") if review["action"] == "change_label" else None
            )
            mapping.update(
                label_codes=[code] if code else [],
                candidate_label_codes=[],
                disposition=None if code else "EXPECTED_ABSTENTION",
                adjudication_action="REPLACE" if code else "ABSTAIN",
                reason=review.get("note") or "人工逐项复核",
            )
        self.result["fact_mappings"] = mappings

    def apply(self) -> dict[str, Any]:
        self._project_units()
        self._project_unknowns()
        self._project_added()
        self._project_facts()
        self.result.update(semantic_units=self.units, unknown_semantics=self.unknowns)
        problems, positives, _negatives = project_review_labels(
            self.units, self.problems, "", ""
        )
        self.result.update(
            problem_label_codes=problems,
            positive_label_codes=positives,
            primary_label_codes=list(dict.fromkeys(self.primary)),
        )
        relations, summary = compile_comment_semantics(
            [
                SemanticUnit.model_validate(
                    {
                        key: value
                        for key, value in unit.items()
                        if key in SemanticUnit.model_fields
                    }
                )
                for unit in self.units
            ],
            self.taxonomy,
            self.labels,
        )
        self.result.update(
            semantic_relations=[item.model_dump(mode="json") for item in relations],
            comment_summary=summary.model_dump(mode="json"),
        )
        return self.result


def apply_semantic_review_changes(
    classification: dict[str, Any],
    taxonomy: TaxonomyConfig,
    comment: str = "",
) -> dict[str, Any]:
    """发布时投影尚未应用的逐项处置；草稿和历史版本保持不变。"""
    entries = [
        *classification.get("human_semantic_reviews", []),
        *classification.get("human_added_semantic_items", []),
    ]
    if not any(not item.get("applied") for item in entries):
        return classification
    return _ReviewProjection(classification, taxonomy, comment).apply()
