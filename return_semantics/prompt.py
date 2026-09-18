from __future__ import annotations

import hashlib
import json

from return_semantics.analysis_context import (
    REVIEW_CONTEXT,
    USER_FEEDBACK_CONTEXT,
    validate_analysis_context,
)
from return_semantics.schemas import ListingClaimsConfig, SubjectCode, TaxonomyConfig
from return_semantics.taxonomy_hierarchy import label_path

PROMPT_VERSION = "category-semantic-v5"


def prompt_version(taxonomy: TaxonomyConfig) -> str:
    return {
        "legacy_v3": PROMPT_VERSION,
        "keyword_free_v1": "category-keyword-free-v3",
        "semantic_v1": "category-semantic-evidence-v3",
        "fact_v2": "category-fact-v2-v33",
    }[taxonomy.recognition_profile]


def recognition_fingerprint(taxonomy: TaxonomyConfig) -> str:
    content = taxonomy.model_dump(mode="json")
    content.pop("version")
    if taxonomy.structure_version == 1:
        # 新增默认字段不能使历史标准的识别缓存失效。
        content.pop("structure_version")
        content.pop("categories")
        for label in content["labels"]:
            label.pop("parent_code")
    if taxonomy.recognition_profile != "legacy_v3":
        for label in content["labels"]:
            label.pop("keywords", None)
    content["prompt_version"] = prompt_version(taxonomy)
    content["validator_version"] = {
        "semantic_v1": "evidence-validator-v2",
        "fact_v2": "evidence-fact-validator-v11",
    }.get(taxonomy.recognition_profile, "evidence-validator-v1")
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
        if (
            taxonomy.structure_version == 1
            and taxonomy.recognition_profile != "semantic_v1"
        ):
            fields = [
                label.code,
                " → ".join(label_path(taxonomy, label.code)),
                label.description,
                sentiments,
            ]
            if taxonomy.recognition_profile == "legacy_v3":
                fields.append(",".join(label.keywords))
            lines.append("|".join(fields))
            continue
        entry = {
            "编码": label.code,
            "名称": label.name,
            "完整路径": label_path(taxonomy, label.code),
            "允许评价方向": sentiments,
        }
        if label.description.strip():
            entry["判定说明"] = label.description
        if taxonomy.recognition_profile == "legacy_v3" and label.keywords:
            entry["英文关键词"] = label.keywords
        if label.exclusions:
            entry["排除说明"] = label.exclusions
        if label.examples:
            entry["判定示例"] = [
                item.model_dump(mode="json") for item in label.examples
            ]
        if label.allowed_claim_ids:
            entry["允许承诺编号"] = label.allowed_claim_ids
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
    context = validate_analysis_context(analysis_context)
    if context == USER_FEEDBACK_CONTEXT:
        task_name = "用户反馈"
        context_rule = (
            "当前是通用用户反馈分析：正向、负向、中性和混合表达都是有效语义，"
            "不得预设用户正在退货、投诉或描述问题。"
        )
    elif context == REVIEW_CONTEXT:
        task_name = "商品评价"
        context_rule = (
            "当前是 Review 评价分析：正向评价不需要解释退货原因，不得虚构退货行为。"
        )
    else:
        task_name = "退货评论"
        context_rule = "当前是退货反馈分析：只有正向体验时，退货原因仍然未知。"
    example_label = taxonomy.labels[0]
    example_sentiment = example_label.allowed_sentiments[0].value
    example_primary = [example_label.code] if example_sentiment == "NEGATIVE" else []
    catalog_format = "每行一个 JSON，判定说明为可选"
    if (
        taxonomy.structure_version == 1
        and taxonomy.recognition_profile != "semantic_v1"
    ):
        catalog_format = "编码|完整路径（末端为标签名称）|判定说明（可空）|允许情感"
        if taxonomy.recognition_profile == "legacy_v3":
            catalog_format += "|英文关键词"
    system_prompt = f"""
你是 Amazon {taxonomy.product_context}{task_name}的语义分类器。只分析客户实际表达的内容。
你的任务是先拆分原子语义，再把每个语义映射到允许的业务标签。
{context_rule}

必须遵守：
1. 评论是唯一的语义证据。不能从标签定义或 Listing 承诺创造问题。
2. evidence 必须逐字复制自输入评论，并且是连续子串。选择能独立支持观点的完整句子或分句，保留评价对象、动作宾语、否定、程度、条件和时间；需要上下文时扩展连续片段，不拼接零散词句。opinion 中每项事实都必须由该 evidence 支持，不从其他未引用句子补入。
3. 一条评论可以有多个语义单元，正面和负面必须分别保留。
4. 根据语义判断 assertion，不按条件词机械判断：带适用条件的真实体验、当前主观评价、明确的条件化购买建议可以是 AFFIRMED，保留其条件与主观语气；尚未发生的预测、假设、担忧及无法确认的指代用 UNCERTAIN 并标记复核。引用他人观点需保留来源并复核，不当作评论者已确认的体验。
5. primary_label_codes 只能包含已确认的负面标签或规则允许的中性买家原因；没有明确主因时留空。
6. 单独的 No 可能是 Amazon 问卷回答，不能自动否定前面的观点。
7. 输入中的结构化品类已经由商品维度确认，不得根据评论重新猜测或改写品类。
8. 只有评论直接支持或反驳承诺时才能填写 claim_id；否则关系为 NONE。
9. 没有合适标签但独立业务语义清晰时写入 unknown_semantics，不得强塞标签。已由具体观点解释的标题总结、原因猜测、后果或被后文实际体验否定的先前担忧，不再重复生成未知语义。
10. 只输出 json，不输出解释或 Markdown。
11. Listing 承诺为“无”时，claim_relation 必须为 NONE，claim_id 必须为 null。
12. 标签名称和完整路径共同表达业务语义，判定说明、排除说明和示例仅补充边界；没有判定说明的标签仍可使用，不得据此认定其语义缺失。
13. 先确认评价针对的商品、配件、使用行为或购买行为。不能把使用方法建议变成购买推荐，也不能把购买意图、客观属性或某对象的好评传播给其他对象或功能；不从品类背景推断原文未说的场景、交通方式或责任。
14. 标题与正文共同描述同一对象、部位、场景下的同一事件时合并一个观点；同一事件的重复措辞不是新事实。不同购买对象、部位、时间阶段、使用场景或独立事件不得机械合并，正负并存时保留各自的对象与条件。
15. 同一事件优先最具体且有直接证据的末端标签，不再追加解释同一事件的笼统质量、适配或整体评价；故障及其后果不重复计数。不同事实即使方向相同仍可分别保留。
16. 输出前逐项核对 label_code 原样来自目录且 sentiment 属于该标签允许方向；不得猜写相似编码，也不得为了保留方向而使用语义不符的标签。
17. 尺码需求或换码偏好本身不等于收到的商品不合身；只有上下文明确描述实际偏大、偏小或其他不合身体验时才归入对应问题。单纯选码需求使用允许的中性标签，未覆盖时保留未知，不按更大或更小的词面反推缺陷。

subject 只能是 {_subject_catalog()}。
sentiment 只能是 NEGATIVE、POSITIVE、NEUTRAL。
assertion 只能是 AFFIRMED、NEGATED、UNCERTAIN。
part 只能是 {_part_catalog(taxonomy)}。
claim_relation 只能是 CONTRADICTS、SUPPORTS、RELATED_UNCERTAIN、NONE。

当前品类规则：
{_instruction_catalog(taxonomy)}

允许的末端标签（{catalog_format}）：
{_label_catalog(taxonomy)}

Listing 承诺（编号|文本|允许标签，仅用于关系判断）：
{_claim_catalog(claims)}

JSON 输出示例：
{{
  "semantic_units": [
    {{
      "subject": "PRODUCT",
      "label_code": "{example_label.code}",
      "opinion": "与所选标签及评价方向一致的原文观点",
      "sentiment": "{example_sentiment}",
      "assertion": "AFFIRMED",
      "part": "UNSPECIFIED",
      "evidence": "原评论中的连续证据",
      "implicit": false,
      "claim_relation": "NONE",
      "claim_id": null
    }}
  ],
  "unknown_semantics": [],
  "primary_label_codes": {json.dumps(example_primary, ensure_ascii=False)},
  "needs_review": false,
  "review_reasons": []
}}
""".strip()

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
- 不要求命中某个单词或示例措辞；同词可以表达不同含义，同义表达可以归入同一标签。
- 标签名称、完整路径、判定说明、排除说明和示例不能作为当前评论的事实。
- 保留明确的年龄、部位和使用时间；缺少商品适用属性时，不推断质量缺陷或描述错误。
- 无法归类时写入 unknown_semantics，semantic_units 中 label_code 必须是非空的有效编码。
未知语义格式示例：
{"semantic_units": [], "unknown_semantics": [{"opinion": "明确表达但暂无适合标签的观点", "evidence": "原文连续片段", "reason": "现有标签定义未覆盖该语义"}], "primary_label_codes": [], "needs_review": true, "review_reasons": ["需确认标签边界"]}
"""
    if taxonomy.structure_version == 2:
        system_prompt += (
            "\n层级判定约束：完整路径说明标签的业务位置，"
            "只能返回目录中的末端标签编码，不能返回分类父节点。"
            "证据仅支持笼统父级而不支持具体末端标签时，写入 unknown_semantics 并标记复核。"
        )
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
