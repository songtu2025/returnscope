/** @typedef {Record<string, any>} SemanticData */

/** @type {Record<string, string>} */
const STATUS_ALIASES = {
  POSITIVE: "POSITIVE",
  ONLY_POSITIVE: "POSITIVE",
  POSITIVE_ONLY: "POSITIVE",
  NEGATIVE: "NEGATIVE",
  ONLY_NEGATIVE: "NEGATIVE",
  NEGATIVE_ONLY: "NEGATIVE",
  MIXED: "MIXED",
  CONDITIONAL: "MIXED",
  CONFLICT: "CONFLICT",
  SUSPECTED_CONFLICT: "CONFLICT",
  NO_CONFIRMED: "NO_CONFIRMED",
  NO_DEFINITE: "NO_CONFIRMED",
  NONE: "NO_CONFIRMED",
  ABSTAINED: "NO_CONFIRMED",
};

/** @type {Record<string, string>} */
export const SEMANTIC_STATUS_LABELS = {
  POSITIVE: "仅正向",
  NEGATIVE: "仅负向",
  MIXED: "混合表现",
  CONFLICT: "疑似冲突",
  NO_CONFIRMED: "无确定评价",
};

/** @type {Record<string, string>} */
const DIRECTION_LABELS = {
  POSITIVE: "正向",
  NEGATIVE: "负向",
  NEUTRAL: "中性",
  MIXED: "混合",
};

/** @type {Record<string, string>} */
const ASSERTION_LABELS = {
  AFFIRMED: "已确认",
  CONFIRMED: "已确认",
  EVALUATION: "当前评价",
  EXPERIENCE: "实际体验",
  PREDICTION: "预测",
  HYPOTHESIS: "假设",
  NOT_TESTED: "未测试",
  NEGATED: "否定陈述",
  REPORTED: "转述",
  INTENT: "意图",
  ADVICE: "建议",
  RECOMMENDATION: "建议",
};

/** @type {Record<string, string>} */
const DISPOSITION_LABELS = {
  TAXONOMY_GAP: "标签体系缺口",
  MAPPING_UNCERTAIN: "标签映射不确定",
  EXPECTED_ABSTENTION: "正常弃权",
  OUT_OF_SCOPE: "超出打标范围",
  EVIDENCE_ONLY: "仅作为证据",
};

const REVIEW_DISPOSITIONS = new Set(["TAXONOMY_GAP", "MAPPING_UNCERTAIN"]);
const INFORMATIONAL_DISPOSITIONS = new Set([
  "EXPECTED_ABSTENTION",
  "OUT_OF_SCOPE",
  "EVIDENCE_ONLY",
]);
/** @type {Record<string, string>} */
const EVIDENCE_SOURCE_LABELS = {
  COMMENT: "评论",
  TITLE: "标题",
  BODY: "正文",
  TITLE_AND_BODY: "标题与正文",
  UNKNOWN: "未提供",
};
/** @type {Record<string, string>} */
const PARTICIPANT_LABELS = {
  REVIEWER: "评论者",
  GIFT_RECIPIENT: "收礼者",
  OTHER_USER: "其他使用者",
  UNKNOWN: "未明确",
};
/** @type {Record<string, string>} */
const REFERENCE_BASIS_LABELS = {
  NONE: "无特定参照",
  PERSONAL_PREFERENCE: "个人偏好",
  SIZE_CHART: "尺码表",
  LISTING: "商品页面",
  MARKET_NORM: "市场正常水平",
  BARE_USE: "裸手使用",
  OTHER_PRODUCT: "其他商品",
  OTHER_PERSON: "其他使用者",
};

/** @type {Record<string, string>} */
const SUBJECT_LABELS = {
  PRODUCT: "当前商品",
  LOGISTICS: "物流",
  PACKAGING: "包装",
  SERVICE: "服务",
  BUYER_REASON: "买家原因",
};

/** @type {Record<string, string>} */
const PRODUCT_REFERENCE_LABELS = {
  CURRENT: "当前商品",
  OTHER: "其他商品",
  PREVIOUS: "旧商品",
  LISTING: "商品页面",
  UNSPECIFIED: "未明确商品",
};

/** @type {Record<string, string>} */
const PART_LABELS = {
  WHOLE_PRODUCT: "商品整体",
  PALM: "掌心",
  BACK_OF_HAND: "手背",
  FINGER: "手指",
  FINGER_GUSSET: "指缝",
  THUMB: "拇指",
  THUMB_WEB: "虎口",
  LINING: "内衬",
  CLOSURE: "闭合结构",
  CUFF: "袖口",
  SEAM: "接缝",
  PACKAGING: "包装",
  ACCESSORY: "配件",
  UNSPECIFIED: "未明确部位",
};

/** @type {Record<string, string>} */
const FACT_RELATION_LABELS = {
  CAUSED_BY: "由关联事实导致",
  COVERED_BY: "已由关联事实覆盖",
  SUPPORTS: "由关联事实支持",
  QUALIFIES: "受关联事实限定",
};

/** @param {any} value @returns {any[]} */
function array(value) {
  return Array.isArray(value) ? value : [];
}

/** @param {SemanticData} record @returns {SemanticData} */
function classificationOf(record) {
  return record?.classification ?? record ?? {};
}

/** @param {any} value @returns {string} */
function normalizedStatus(value) {
  return STATUS_ALIASES[String(value || "").toUpperCase()] || "NO_CONFIRMED";
}

/** @param {SemanticData} fact @returns {string} */
function directionOf(fact) {
  return String(
    fact?.evaluation_direction ?? fact?.sentiment ?? fact?.direction ?? "NEUTRAL",
  ).toUpperCase();
}

/** @param {SemanticData} fact @returns {string} */
function assertionOf(fact) {
  return String(
    fact?.statement_type ??
      fact?.assertion_status ??
      fact?.assertion ??
      fact?.fact_type ??
      "AFFIRMED",
  ).toUpperCase();
}

/** @param {SemanticData} fact @returns {boolean} */
function isConfirmed(fact) {
  return ![
    "PREDICTION",
    "HYPOTHESIS",
    "NOT_TESTED",
    "INTENT",
    "ADVICE",
    "RECOMMENDATION",
  ].includes(assertionOf(fact));
}

/** @param {SemanticData} fact @returns {string[]} */
function pathOf(fact) {
  const path =
    fact?.full_label_path ??
    fact?.label_path ??
    fact?.taxonomy_path ??
    fact?.labelPath ??
    [];
  if (Array.isArray(path)) return path.filter(Boolean);
  if (typeof path === "string") {
    return path
      .split(/\s*(?:→|>|\/|-)\s*/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
}

/** @param {any} value @returns {string} */
function conditionText(value) {
  if (!value) return "";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.filter(Boolean).join("、");
  if (typeof value === "object") {
    return Object.values(value).map(conditionText).filter(Boolean).join("；");
  }
  return String(value);
}

/** @param {...any} values @returns {any} */
function firstValue(...values) {
  return values.find(
    (value) => value !== undefined && value !== null && String(value).trim(),
  );
}

/**
 * @param {SemanticData} fact
 * @param {number} index
 * @param {SemanticData} [scope]
 * @returns {SemanticData}
 */
function normalizedFact(fact, index, scope = {}) {
  const evidenceSpans = array(fact?.evidence_spans);
  return {
    ...fact,
    factId:
      fact?.fact_id ?? fact?.fact_ids?.[0] ?? fact?.source_fact_id ?? fact?.id ?? "",
    labelCode: fact?.label_code ?? fact?.verdict_label_code ?? fact?.labelCode ?? "",
    labelPath: pathOf(fact),
    opinion: firstValue(
      fact?.opinion,
      fact?.fact_text_zh,
      fact?.fact_summary,
      fact?.summary,
    ),
    subject: firstValue(fact?.subject, fact?.object_type, fact?.scope?.subject),
    direction: directionOf(fact),
    assertion: assertionOf(fact),
    sourceRef: firstValue(
      scope.source_ref,
      fact?.source_ref,
      fact?.scope?.source_ref,
      fact?.sourceRef,
    ),
    experiencerRef: firstValue(
      scope.experiencer_ref,
      scope.actor_ref,
      fact?.experiencer_ref,
      fact?.actor_ref,
      fact?.actor,
      fact?.scope?.experiencer_ref,
      fact?.scope?.actor,
      fact?.experiencerRef,
    ),
    productRef: firstValue(
      scope.product_ref,
      fact?.product_ref,
      fact?.scope?.product_ref,
      fact?.productRef,
    ),
    variantRef: firstValue(
      scope.variant_ref,
      fact?.variant_ref,
      fact?.scope?.variant_ref,
      fact?.variantRef,
    ),
    eventRef: firstValue(
      scope.event_ref,
      fact?.event_ref,
      fact?.event_id,
      fact?.scope?.event_ref,
      fact?.eventRef,
    ),
    referenceBasis: firstValue(
      scope.reference_basis,
      fact?.reference_basis,
      fact?.scope?.reference_basis,
      fact?.referenceBasis,
    ),
    condition: conditionText(
      firstValue(
        scope.condition,
        fact?.condition,
        fact?.conditions,
        fact?.scope?.condition,
      ),
    ),
    operation: firstValue(scope.operation, fact?.operation, fact?.scope?.operation),
    part: firstValue(scope.part, fact?.part, fact?.scope?.part),
    evidence:
      fact?.evidence ??
      fact?.evidence_text ??
      fact?.text ??
      evidenceSpans
        .map((span) => span?.text)
        .filter(Boolean)
        .join(" … "),
    evidenceSource:
      fact?.evidence_source ??
      fact?.source ??
      fact?.evidenceSource ??
      evidenceSpans
        .map((span) => span?.source)
        .filter(Boolean)
        .join("+") ??
      "",
    decisionReason: firstValue(
      fact?.decision_reason,
      fact?.verdict_reason,
      fact?.decisionReason,
    ),
    mappingReason: firstValue(fact?.mapping_reason, fact?.mappingReason, fact?.reason),
    relationType: String(
      firstValue(fact?.relation_type, fact?.fact_relation_type, fact?.relationType) ||
        "",
    ).toUpperCase(),
    relatedFactIds: array(
      fact?.related_fact_ids ?? fact?.cause_fact_ids ?? fact?.relatedFactIds,
    ),
    causalAttribution: firstValue(
      fact?.causal_attribution,
      fact?.cause_attribution,
      fact?.cause_actor,
      fact?.cause_ref,
      fact?.cause,
      fact?.causalAttribution,
    ),
    position: index,
  };
}

/** @param {SemanticData} classification @param {SemanticData} record @returns {any[][]} */
function factSources(classification, record) {
  return [
    record?.atomic_facts,
    record?.semantic_units,
    classification.atomic_facts,
    classification.semantic_units,
    record?.semantic_facts,
    classification.semantic_facts,
    record?.extracted_facts,
    classification.extracted_facts,
    record?.facts,
    classification.facts,
    record?.evidence,
  ].filter(Array.isArray);
}

/** @param {SemanticData} classification @param {SemanticData} record @returns {SemanticData[]} */
function mappingSources(classification, record) {
  return array(record?.fact_mappings ?? classification.fact_mappings);
}

/** @param {any} value @returns {boolean} */
function meaningful(value) {
  return value !== undefined && value !== null && value !== "";
}

/** @param {SemanticData} primary @param {SemanticData} secondary @returns {SemanticData} */
function mergeFacts(primary, secondary) {
  const merged = { ...primary };
  Object.entries(secondary).forEach(([key, value]) => {
    if (
      !meaningful(merged[key]) ||
      (Array.isArray(merged[key]) && !merged[key].length)
    ) {
      merged[key] = value;
    }
  });
  return merged;
}

/** @param {SemanticData} classification @param {SemanticData} record @returns {SemanticData[]} */
function sourceFacts(classification, record) {
  const identified = new Map();
  /** @type {SemanticData[]} */
  const anonymous = [];
  factSources(classification, record).forEach((facts) => {
    facts.forEach((fact, index) => {
      const normalized = normalizedFact(fact, index);
      if (!normalized.factId) {
        anonymous.push(normalized);
        return;
      }
      identified.set(
        normalized.factId,
        mergeFacts(identified.get(normalized.factId) ?? {}, normalized),
      );
    });
  });
  const mappings = new Map(
    mappingSources(classification, record).map((mapping) => [mapping.fact_id, mapping]),
  );
  return [...identified.values(), ...anonymous].map((fact) => {
    const mapping = mappings.get(fact.factId);
    if (!mapping) return fact;
    return mergeFacts(fact, {
      mappingReason: mapping.reason,
      relationType: mapping.relation_type,
      relatedFactIds: array(mapping.related_fact_ids),
    });
  });
}

/** @param {SemanticData} classification @param {SemanticData} record @returns {any[]} */
function conclusionSources(classification, record) {
  return (
    record?.comment_conclusions ??
    record?.aspect_summaries ??
    record?.semantic_summaries ??
    record?.topic_summaries ??
    classification.comment_conclusions ??
    classification.aspect_summaries ??
    classification.semantic_summaries ??
    classification.topic_summaries ??
    []
  );
}

/** @param {SemanticData} classification @param {SemanticData} record @returns {any[]} */
function dimensionDecisionSources(classification, record) {
  return record?.dimension_decisions ?? classification.dimension_decisions ?? [];
}

/** @param {SemanticData} fact @returns {string} */
function scopeKey(fact) {
  return [
    fact.sourceRef,
    fact.experiencerRef,
    fact.productRef,
    fact.variantRef,
    fact.eventRef,
    fact.referenceBasis,
    fact.part,
    fact.operation,
    fact.condition,
  ]
    .map((value) => String(value || "").trim())
    .join("|");
}

/** @param {SemanticData[]} facts @returns {string} */
function derivedConclusionStatus(facts) {
  const confirmed = facts.filter(isConfirmed);
  const positive = confirmed.filter((fact) => fact.direction === "POSITIVE");
  const negative = confirmed.filter((fact) => fact.direction === "NEGATIVE");
  if (!positive.length && !negative.length) return "NO_CONFIRMED";
  if (!negative.length) return "POSITIVE";
  if (!positive.length) return "NEGATIVE";
  const negativeScopes = new Set(negative.map(scopeKey));
  const sameScopeConflict = positive.some((fact) => negativeScopes.has(scopeKey(fact)));
  return sameScopeConflict ? "CONFLICT" : "MIXED";
}

/** @param {SemanticData} fact @returns {SemanticData} */
function topicForFact(fact) {
  const explicit =
    fact.aspect_label ??
    fact.aspect_name ??
    fact.topic_label ??
    fact.aspect ??
    fact.topic;
  if (explicit) {
    return {
      key: fact.aspect_code ?? fact.topic_code ?? explicit,
      label: explicit,
      path: array(fact.aspect_path),
    };
  }
  const topicPath = fact.labelPath.length > 1 ? fact.labelPath.slice(0, -1) : [];
  return {
    key: topicPath.join("/") || fact.labelCode || "未归类主题",
    label: topicPath.at(-1) || fact.labelCode || "未归类主题",
    path: topicPath,
  };
}

/** @param {SemanticData[]} facts @param {boolean} [legacy] @returns {SemanticData[]} */
function deriveConclusions(facts, legacy = true) {
  const groups = new Map();
  facts
    .filter((fact) => fact.labelCode || fact.labelPath.length)
    .forEach((fact) => {
      const topic = topicForFact(fact);
      const current = groups.get(topic.key) ?? { ...topic, facts: [] };
      current.facts.push(fact);
      groups.set(topic.key, current);
    });
  return [...groups.values()].map((group) => ({
    id: group.key,
    topic: group.label,
    topicPath: group.path,
    status: derivedConclusionStatus(group.facts),
    summary: "",
    facts: group.facts,
    contextFacts: [],
    legacy,
  }));
}

/** @param {SemanticData} conclusion @param {number} index @param {SemanticData[]} allFacts @returns {SemanticData} */
function normalizeConclusion(conclusion, index, allFacts) {
  const factIds = array(conclusion.supporting_fact_ids ?? conclusion.fact_ids);
  const labelCodes = array(conclusion.label_codes);
  const embeddedFacts = array(conclusion.facts ?? conclusion.atomic_facts).map(
    normalizedFact,
  );
  const matchedById = factIds.length
    ? allFacts.filter((fact) => factIds.includes(fact.factId))
    : [];
  const matchedByLabel = allFacts.filter((fact) => labelCodes.includes(fact.labelCode));
  const topicIdentities = new Set(
    [
      conclusion.aspect_code,
      conclusion.topic_code,
      conclusion.aspect_label,
      conclusion.aspect_name,
      conclusion.topic_label,
      conclusion.topic_name,
      ...array(conclusion.aspect_path),
      ...array(conclusion.topic_path),
    ]
      .filter(Boolean)
      .map(String),
  );
  const matchedByTopic = allFacts.filter((fact) => {
    const topic = topicForFact(fact);
    return [topic.key, topic.label, ...topic.path].some((value) =>
      topicIdentities.has(String(value)),
    );
  });
  const matchedFacts = matchedById.length
    ? matchedById
    : matchedByLabel.length
      ? matchedByLabel
      : matchedByTopic;
  const facts = embeddedFacts.length ? embeddedFacts : matchedFacts;
  const topicPath = array(conclusion.aspect_path ?? conclusion.topic_path).filter(
    Boolean,
  );
  return {
    id:
      conclusion.id ??
      conclusion.aspect_code ??
      conclusion.topic_code ??
      `topic-${index}`,
    topic:
      conclusion.aspect_label ??
      conclusion.aspect_name ??
      conclusion.topic_label ??
      conclusion.topic_name ??
      conclusion.label ??
      topicPath.at(-1) ??
      "未归类主题",
    topicPath,
    status: normalizedStatus(
      conclusion.summary_status ?? conclusion.status ?? conclusion.sentiment_status,
    ),
    summary: conclusion.summary ?? conclusion.statement ?? conclusion.conclusion ?? "",
    facts,
    contextFacts: [],
    legacy: facts.some((fact) =>
      [
        fact.sourceRef,
        fact.experiencerRef,
        fact.productRef,
        fact.variantRef,
        fact.eventRef,
        fact.referenceBasis,
      ].some((value) => !meaningful(value)),
    ),
  };
}

/** @param {SemanticData[]} decisions @param {SemanticData[]} allFacts @returns {SemanticData} */
function decisionConclusions(decisions, allFacts) {
  const groups = new Map();
  const consumedFactIds = new Set();
  decisions.forEach((decision, index) => {
    const supportingIds = array(decision.supporting_fact_ids);
    const contextIds = array(decision.context_fact_ids);
    supportingIds.forEach((factId) => consumedFactIds.add(factId));
    contextIds.forEach((factId) => consumedFactIds.add(factId));
    const supportingFacts = supportingIds.map((factId) => {
      const matched = allFacts.find((fact) => fact.factId === factId) ?? {
        fact_id: factId,
      };
      return normalizedFact(
        {
          ...matched,
          label_code: decision.verdict_label_code,
          decision_reason: decision.reason,
        },
        index,
        decision.scope,
      );
    });
    const contextFacts = contextIds.map((factId) => {
      const matched = allFacts.find((fact) => fact.factId === factId) ?? {
        fact_id: factId,
      };
      return normalizedFact(matched, index, decision.scope);
    });
    const verdictFact =
      supportingFacts.find((fact) => fact.labelCode === decision.verdict_label_code) ??
      allFacts.find((fact) => fact.labelCode === decision.verdict_label_code);
    const topic = topicForFact(verdictFact ?? supportingFacts[0] ?? {});
    const key = decision.parent_code || topic.key || `decision-${index}`;
    const current = groups.get(key) ?? {
      id: key,
      topic: topic.label || key,
      topicPath: topic.path,
      summary: "",
      facts: [],
      contextFacts: [],
      reasons: [],
      legacy: false,
    };
    current.facts.push(...supportingFacts);
    current.contextFacts.push(...contextFacts);
    if (decision.reason) current.reasons.push(decision.reason);
    groups.set(key, current);
  });
  return {
    conclusions: [...groups.values()].map((group) => ({
      ...group,
      status: derivedConclusionStatus(group.facts),
      summary: group.reasons.join("；"),
    })),
    consumedFactIds,
  };
}

/** @param {SemanticData} record @returns {SemanticData[]} */
export function semanticConclusions(record) {
  const classification = classificationOf(record);
  const facts = sourceFacts(classification, record);
  const decisions = array(dimensionDecisionSources(classification, record));
  if (decisions.length) {
    const { conclusions, consumedFactIds } = decisionConclusions(decisions, facts);
    const residual = facts.filter(
      (fact) =>
        !consumedFactIds.has(fact.factId) && (fact.labelCode || fact.labelPath.length),
    );
    return [...conclusions, ...deriveConclusions(residual, false)];
  }
  const provided = array(conclusionSources(classification, record));
  return provided.length
    ? provided.map((conclusion, index) => normalizeConclusion(conclusion, index, facts))
    : deriveConclusions(facts);
}

/** @param {SemanticData} record @returns {string} */
export function semanticRecordStatus(record) {
  const classification = classificationOf(record);
  const explicit =
    record?.comment_summary_status ??
    record?.comment_summary?.status ??
    record?.semantic_status ??
    classification.comment_summary_status ??
    classification.comment_summary?.status ??
    classification.semantic_status;
  if (explicit) return normalizedStatus(explicit);
  const statuses = semanticConclusions(record).map((item) => item.status);
  if (statuses.includes("CONFLICT")) return "CONFLICT";
  if (statuses.includes("MIXED")) return "MIXED";
  if (statuses.includes("POSITIVE") && statuses.includes("NEGATIVE")) return "MIXED";
  if (statuses.includes("NEGATIVE")) return "NEGATIVE";
  if (statuses.includes("POSITIVE")) return "POSITIVE";
  return "NO_CONFIRMED";
}

/** @param {SemanticData} record @returns {SemanticData[]} */
export function semanticRelations(record) {
  const classification = classificationOf(record);
  const relations = record?.semantic_relations ?? classification.semantic_relations;
  return array(relations).map((relation, index) => ({
    id: relation.id ?? `relation-${index}`,
    type: String(relation.relation_type ?? relation.type ?? "").toUpperCase(),
    reason: relation.reason ?? "未提供关系说明",
    factIds: array(relation.fact_ids),
  }));
}

/** @param {any} unknown @param {number} index @param {string} [fallbackDisposition] @returns {SemanticData} */
function normalizeUnknown(unknown, index, fallbackDisposition = "") {
  const item =
    typeof unknown === "string" ? { opinion: unknown, evidence: unknown } : unknown;
  const normalized = normalizedFact(item ?? {}, index);
  const disposition = String(item?.disposition || fallbackDisposition).toUpperCase();
  return {
    ...normalized,
    id: normalized.factId || `unknown-${index}`,
    opinion: item?.opinion ?? item?.text ?? "",
    reason: item?.reason ?? "",
    disposition,
    dispositionLabel: disposition
      ? DISPOSITION_LABELS[disposition] || disposition
      : "旧结果未提供处置",
    legacyDisposition: !disposition,
  };
}

/** @param {SemanticData} item @returns {string} */
function unknownIdentity(item) {
  if (item.factId) return `fact:${item.factId}`;
  return [
    item.opinion,
    item.evidence,
    item.sourceRef,
    item.experiencerRef,
    item.productRef,
    item.variantRef,
    item.eventRef,
    item.operation,
    item.condition,
  ]
    .map((value) => String(value || "").trim())
    .join("|");
}

/** @param {SemanticData} record @returns {{review: SemanticData[], informational: SemanticData[]}} */
export function semanticUnknownGroups(record) {
  const classification = classificationOf(record);
  const sources = [
    ...array(record?.unknown_semantics).map((item) => [item, ""]),
    ...array(classification.unknown_semantics).map((item) => [item, ""]),
    ...array(record?.ignored_semantics).map((item) => [item, "EXPECTED_ABSTENTION"]),
    ...array(classification.ignored_semantics).map((item) => [
      item,
      "EXPECTED_ABSTENTION",
    ]),
  ];
  const seen = new Set();
  const unknowns = sources
    .map(([item, fallbackDisposition], index) =>
      normalizeUnknown(item, index, fallbackDisposition),
    )
    .filter((item) => {
      const identity = unknownIdentity(item);
      if (seen.has(identity)) return false;
      seen.add(identity);
      return true;
    });
  /** @type {{review: SemanticData[], informational: SemanticData[]}} */
  const groups = { review: [], informational: [] };
  unknowns.forEach((item) => {
    if (INFORMATIONAL_DISPOSITIONS.has(item.disposition)) {
      groups.informational.push(item);
    } else if (REVIEW_DISPOSITIONS.has(item.disposition) || !item.disposition) {
      groups.review.push(item);
    } else {
      groups.review.push(item);
    }
  });
  return groups;
}

/** @param {any} status @returns {string} */
export function semanticStatusLabel(status) {
  return SEMANTIC_STATUS_LABELS[normalizedStatus(status)];
}

/** @param {any} value @returns {string} */
function participantLabel(value) {
  return PARTICIPANT_LABELS[value] || value;
}

/** @param {SemanticData} fact @returns {SemanticData} */
export function factPresentation(fact) {
  const normalized = normalizedFact(fact, 0);
  const relatedFacts = normalized.relatedFactIds.join("、");
  const causalAttribution =
    normalized.causalAttribution ||
    (normalized.relationType === "CAUSED_BY" && relatedFacts
      ? `${FACT_RELATION_LABELS.CAUSED_BY}：${relatedFacts}`
      : "");
  return {
    ...normalized,
    directionLabel: DIRECTION_LABELS[normalized.direction] || normalized.direction,
    assertionLabel: ASSERTION_LABELS[normalized.assertion] || normalized.assertion,
    sourceLabel: participantLabel(normalized.sourceRef),
    experiencerLabel: participantLabel(normalized.experiencerRef),
    evidenceSourceLabel:
      EVIDENCE_SOURCE_LABELS[normalized.evidenceSource] || normalized.evidenceSource,
    referenceBasisLabel:
      REFERENCE_BASIS_LABELS[normalized.referenceBasis] || normalized.referenceBasis,
    subjectLabel: SUBJECT_LABELS[normalized.subject] || normalized.subject,
    productLabel:
      PRODUCT_REFERENCE_LABELS[normalized.productRef] || normalized.productRef,
    partLabel: PART_LABELS[normalized.part] || normalized.part,
    causalAttribution,
    decisionReason: normalized.decisionReason || normalized.mappingReason,
  };
}
