from __future__ import annotations

from return_semantics.fact_prompts import _messages

__ADJUDICATION_INSTRUCTION = (
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
    "reason用中文简述裁决依据，不得用reason改变结构化事实。"
)


__MAPPING_INSTRUCTION = (
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
    "目录和品类规则只解释标签边界，不能创造评论事实。"
)


def _adjudication_messages(payload: dict) -> list[dict[str, str]]:
    return _messages(
        __ADJUDICATION_INSTRUCTION,
        payload,
    )


def _mapping_messages(payload: dict) -> list[dict[str, str]]:
    return _messages(
        __MAPPING_INSTRUCTION,
        payload,
    )
