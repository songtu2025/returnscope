from __future__ import annotations

import hashlib
import json

from return_semantics.schemas import ListingClaimsConfig, SubjectCode, TaxonomyConfig

PROMPT_VERSION = "category-semantic-v3"


def prompt_version(taxonomy: TaxonomyConfig) -> str:
    return {
        "legacy_v3": PROMPT_VERSION,
        "keyword_free_v1": "category-keyword-free-v1",
        "semantic_v1": "category-semantic-evidence-v1",
    }[taxonomy.recognition_profile]


def recognition_fingerprint(taxonomy: TaxonomyConfig) -> str:
    content = taxonomy.model_dump(mode="json")
    content.pop("version")
    if taxonomy.recognition_profile != "legacy_v3":
        for label in content["labels"]:
            label.pop("keywords", None)
    content["prompt_version"] = prompt_version(taxonomy)
    content["validator_version"] = (
        "evidence-validator-v2"
        if taxonomy.recognition_profile == "semantic_v1"
        else "evidence-validator-v1"
    )
    return hashlib.sha256(
        json.dumps(
            content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _label_catalog(taxonomy: TaxonomyConfig) -> str:
    lines = []
    for label in taxonomy.labels:
        sentiments = ",".join(value.value for value in label.allowed_sentiments)
        if taxonomy.recognition_profile == "legacy_v3":
            keywords = ",".join(label.keywords) or "无"
            lines.append(f"{label.code}|{label.description}|{keywords}|{sentiments}")
        elif taxonomy.recognition_profile == "keyword_free_v1":
            lines.append(f"{label.code}|{label.description}|{sentiments}")
        else:
            entry = {
                "编码": label.code,
                "名称": label.name,
                "定义": label.description,
                "允许评价方向": sentiments,
            }
            if label.exclusions:
                entry["排除说明"] = label.exclusions
            if label.examples:
                entry["判定示例"] = [
                    item.model_dump(mode="json") for item in label.examples
                ]
            lines.append(json.dumps(entry, ensure_ascii=False))
    return "\n".join(lines)


def _claim_catalog(claims: ListingClaimsConfig) -> str:
    if not claims.claims:
        return "无"

    lines = []
    for claim in claims.claims:
        allowed_labels = ",".join(claim.allowed_label_codes)
        lines.append(f"{claim.claim_id}|{claim.text}|{allowed_labels}")
    return "\n".join(lines)


def _part_catalog(taxonomy: TaxonomyConfig) -> str:
    return "、".join(taxonomy.allowed_parts)


def _subject_catalog() -> str:
    return "、".join(subject.value for subject in SubjectCode)


def _instruction_catalog(taxonomy: TaxonomyConfig) -> str:
    if not taxonomy.instructions:
        return "无额外品类规则"
    return "\n".join(
        f"{index}. {instruction}"
        for index, instruction in enumerate(taxonomy.instructions, start=1)
    )


def build_messages(
    comment: str,
    taxonomy: TaxonomyConfig,
    claims: ListingClaimsConfig,
    category_context: dict[str, str] | None = None,
    analysis_context: str = "returns",
) -> list[dict[str, str]]:
    task_name = "商品评价" if analysis_context == "review" else "退货评论"
    context_rule = (
        "当前是 Review 评价分析：正向评价不需要解释退货原因，不得虚构退货行为。"
        if analysis_context == "review"
        else "当前是退货反馈分析：只有正向体验时，退货原因仍然未知。"
    )
    system_prompt = f"""
你是 Amazon {taxonomy.product_context}{task_name}的语义分类器。只分析客户实际表达的内容。
你的任务是先拆分原子语义，再把每个语义映射到允许的业务标签。
{context_rule}

必须遵守：
1. 评论是唯一的语义证据。不能从标签定义或 Listing 承诺创造问题。
2. evidence 必须逐字复制自输入评论，并且是连续子串。
3. 一条评论可以有多个语义单元，正面和负面必须分别保留。
4. 不确定、引用他人观点、条件句和无法确认的指代要标记复核。
5. primary_label_codes 只能包含已确认的负面标签或规则允许的中性买家原因；没有明确主因时留空。
6. 单独的 No 可能是 Amazon 问卷回答，不能自动否定前面的观点。
7. 输入中的结构化品类已经由商品维度确认，不得根据评论重新猜测或改写品类。
8. 只有评论直接支持或反驳承诺时才能填写 claim_id；否则关系为 NONE。
9. 没有合适标签但语义清晰时写入 unknown_semantics，不得强塞标签。
10. 只输出 json，不输出解释或 Markdown。
11. Listing 承诺为“无”时，claim_relation 必须为 NONE，claim_id 必须为 null。

subject 只能是 {_subject_catalog()}。
sentiment 只能是 NEGATIVE、POSITIVE、NEUTRAL。
assertion 只能是 AFFIRMED、NEGATED、UNCERTAIN。
part 只能是 {_part_catalog(taxonomy)}。
claim_relation 只能是 CONTRADICTS、SUPPORTS、RELATED_UNCERTAIN、NONE。

当前品类规则：
{_instruction_catalog(taxonomy)}

允许的标签（编码|定义|英文关键词|允许情感）：
{_label_catalog(taxonomy)}

Listing 承诺（编号|文本|允许标签，仅用于关系判断）：
{_claim_catalog(claims)}

JSON 输出示例：
{{
  "semantic_units": [
    {{
      "subject": "PRODUCT",
      "label_code": "{taxonomy.labels[0].code}",
      "opinion": "商品存在明确问题",
      "sentiment": "NEGATIVE",
      "assertion": "AFFIRMED",
      "part": "UNSPECIFIED",
      "evidence": "原评论中的连续证据",
      "implicit": false,
      "claim_relation": "NONE",
      "claim_id": null
    }}
  ],
  "unknown_semantics": [],
  "primary_label_codes": ["{taxonomy.labels[0].code}"],
  "needs_review": false,
  "review_reasons": []
}}
""".strip()

    if taxonomy.recognition_profile != "legacy_v3":
        system_prompt = system_prompt.replace(
            "编码|定义|英文关键词|允许情感", "编码|定义|允许情感"
        )
    if taxonomy.recognition_profile == "semantic_v1":
        for field in (
            "evidence_requirements",
            "implicit_evidence_rules",
            "claim_evidence_requirements",
        ):
            for rule in getattr(taxonomy.validation_rules, field):
                if rule.semantic_requirement:
                    system_prompt += (
                        f"\n{rule.label_code} 的语义边界：{rule.semantic_requirement}"
                    )
        system_prompt += """

语义判定约束：
- 先理解完整评论中的对象、事件、评价方向、否定、条件和时间关系，再映射标签。
- 不要求命中某个单词或示例措辞；同词可以表达不同含义，同义表达可以归入同一标签。
- 标签名称、定义、排除说明和示例仅解释边界，不能作为当前评论的事实。
- 区分实际发生、否定发生、未来担忧、他人观点和不同购买批次；不得合并独立事件。
- 证据必须包含决定判断的否定、限定或条件上下文，不能截取单个词来改变原意。
- 保留明确的年龄、部位和使用时间；缺少商品适用属性时，不推断质量缺陷或描述错误。
- 无法归类时写入 unknown_semantics，semantic_units 中 label_code 必须是非空的有效编码。
未知语义格式示例：
{"semantic_units": [], "unknown_semantics": [{"opinion": "明确表达但暂无适合标签的观点", "evidence": "原文连续片段", "reason": "现有标签定义未覆盖该语义"}], "primary_label_codes": [], "needs_review": true, "review_reasons": ["需确认标签边界"]}
"""
    user_prompt = json.dumps(
        {
            "category": category_context or {},
            "comment": comment,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def validation_contract_matches(snapshot: dict, source: dict) -> bool:
    taxonomy = TaxonomyConfig.model_validate(snapshot["taxonomy"])
    if source.get("comparison_type", "standard_version") != "standard_version":
        return False
    contract = source.get("recognition_contract")
    if not contract:
        return taxonomy.recognition_profile == "legacy_v3"
    return contract["candidate"]["fingerprint"] == recognition_fingerprint(taxonomy)
