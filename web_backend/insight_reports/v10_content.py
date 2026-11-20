import json
from typing import Any, Literal

from pydantic import BaseModel

from web_backend.insight_reports.v9_content import _with_narrative


class Metric(BaseModel):
    label: str
    numerator: int
    denominator: int
    unit: Literal["条"]
    percent: float | None
    scope: str


class RepresentativeRecord(BaseModel):
    record_id: str
    source_record_id: str | None
    result_version_id: str
    source_row: int | None
    excerpt: str
    date: str | None
    product: str | None
    mapping_status: str | None
    review_status: str | None
    reason: str


class Chapter(BaseModel):
    id: str
    name: str
    title: str
    metrics: list[Metric]
    breakdown: list[Metric]
    boundary: str
    definition: str
    explanation: str
    action: str
    records: list[RepresentativeRecord]


class ActionDecision(BaseModel):
    priority: Literal["P0", "P1"]
    chapter_id: str
    output: str
    decision: str


class SummaryItem(BaseModel):
    label: str
    text: str


class VerifiableReportContent(BaseModel):
    report_type: Literal["verifiable_insight"]
    title: str
    summary: list[SummaryItem]
    chapters: list[Chapter]
    actions: list[ActionDecision]
    boundaries: list[str]


def verifiable_messages(evidence: dict[str, Any]) -> list[dict[str, str]]:
    chapters = evidence["blueprint"]["verifiable"]["chapters"]
    return [
        {
            "role": "system",
            "content": (
                "给产品经理写各章解释与下一步。只允许解释已提供事实，行动写明对照方法；"
                "每项一条中文短句，不加数字、结论、产品名称、时间、故障率或记录，不重复标题。"
                "返回 JSON 对象 chapters 数组，每项含 id、explanation、action、evidence_ids，"
                "evidence_ids 仅使用对应章节 id。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                [
                    {
                        key: chapter[key]
                        for key in (
                            "id",
                            "title",
                            "metrics",
                            "boundary",
                            "explanation",
                            "action",
                        )
                    }
                    for chapter in chapters
                ],
                ensure_ascii=False,
            ),
        },
    ]


def assemble_verifiable(
    evidence: dict[str, Any], payload: Any
) -> VerifiableReportContent:
    blueprint = evidence["blueprint"]["verifiable"]
    proposed = payload.get("chapters") if isinstance(payload, dict) else None
    chapters = [
        {**chapter, "evidence_ids": [chapter["id"]]}
        for chapter in blueprint["chapters"]
    ]
    chapters = _with_narrative(
        _with_narrative(chapters, proposed, "explanation"), proposed, "action"
    )
    return VerifiableReportContent.model_validate({**blueprint, "chapters": chapters})
