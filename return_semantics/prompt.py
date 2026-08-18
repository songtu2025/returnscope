from __future__ import annotations

import json

from return_semantics.schemas import ListingClaimsConfig, TaxonomyConfig

PROMPT_VERSION = "category-semantic-v1"


def _label_catalog(taxonomy: TaxonomyConfig) -> str:
    lines = []
    for label in taxonomy.labels:
        sentiments = ",".join(value.value for value in label.allowed_sentiments)
        lines.append(f"{label.code}|{label.description}|{sentiments}")
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
    return "、".join(part.value for part in taxonomy.allowed_parts)


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
) -> list[dict[str, str]]:
    system_prompt = f"""
你是 Amazon {taxonomy.product_context}退货评论的语义分类器。只分析客户实际表达的内容。
你的任务是先拆分原子语义，再把每个语义映射到允许的业务标签。

必须遵守：
1. 评论是唯一的语义证据。不能从标签定义或 Listing 承诺创造问题。
2. evidence 必须逐字复制自输入评论，并且是连续子串。
3. 一条评论可以有多个语义单元，正面和负面必须分别保留。
4. 不确定、引用他人观点、条件句和无法确认的指代要标记复核。
5. primary_label_codes 只能包含已确认的负面标签；没有明确主因时留空。
6. 单独的 No 可能是 Amazon 问卷回答，不能自动否定前面的观点。
7. 输入中的结构化品类已经由商品维度确认，不得根据评论重新猜测或改写品类。
8. 只有评论直接支持或反驳承诺时才能填写 claim_id；否则关系为 NONE。
9. 没有合适标签但语义清晰时写入 unknown_semantics，不得强塞标签。
10. 只输出 json，不输出解释或 Markdown。
11. Listing 承诺为“无”时，claim_relation 必须为 NONE，claim_id 必须为 null。

subject 只能是 PRODUCT、CUSTOMER、DELIVERY、ORDER、UNKNOWN。
sentiment 只能是 NEGATIVE、POSITIVE、NEUTRAL。
assertion 只能是 AFFIRMED、NEGATED、UNCERTAIN。
part 只能是 {_part_catalog(taxonomy)}。
claim_relation 只能是 CONTRADICTS、SUPPORTS、RELATED_UNCERTAIN、NONE。

当前品类规则：
{_instruction_catalog(taxonomy)}

允许的标签（编码|定义|允许情感）：
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
