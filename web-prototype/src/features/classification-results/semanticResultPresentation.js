/**
 * @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultRecordResponse} GeneratedRecord
 * @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationSemanticFactResponse} GeneratedFact
 * @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationUnknownSemanticResponse} GeneratedUnknownSemantic
 * @typedef {Record<string, unknown>} SemanticObject
 * @typedef {GeneratedRecord | SemanticObject} SemanticRecord
 * @typedef {GeneratedFact | SemanticObject} RawFact
 * @typedef {GeneratedUnknownSemantic | SemanticObject | string} RawUnknownSemantic
 * @typedef {"POSITIVE" | "NEGATIVE" | "MIXED" | "CONFLICT" | "NO_CONFIRMED"} SemanticStatus
 * @typedef {{
 *   factId: string,
 *   labelCode: string,
 *   labelPath: string[],
 *   opinion: string,
 *   subject: string,
 *   direction: string,
 *   assertion: string,
 *   sourceRef: string,
 *   experiencerRef: string,
 *   productRef: string,
 *   variantRef: string,
 *   eventRef: string,
 *   referenceBasis: string,
 *   condition: string,
 *   operation: string,
 *   part: string,
 *   evidence: string,
 *   evidenceSource: string,
 *   decisionReason: string,
 *   mappingReason: string,
 *   relationType: string,
 *   relatedFactIds: string[],
 *   causalAttribution: string,
 *   position: number
 * }} NormalizedFactFields
 * @typedef {SemanticObject & NormalizedFactFields} NormalizedFact
 * @typedef {NormalizedFact & {
 *   directionLabel: string,
 *   assertionLabel: string,
 *   sourceLabel: string,
 *   experiencerLabel: string,
 *   evidenceSourceLabel: string,
 *   referenceBasisLabel: string,
 *   subjectLabel: string,
 *   productLabel: string,
 *   partLabel: string
 * }} PresentedFact
 * @typedef {{ key: string, label: string, path: string[] }} SemanticTopic
 * @typedef {{
 *   id: string,
 *   topic: string,
 *   topicPath: string[],
 *   status: SemanticStatus,
 *   summary: string,
 *   facts: NormalizedFact[],
 *   contextFacts: NormalizedFact[],
 *   legacy: boolean
 * }} SemanticConclusion
 * @typedef {{ id: string, type: string, reason: string, factIds: string[] }} SemanticRelation
 * @typedef {NormalizedFact & {
 *   id: string,
 *   disposition: string,
 *   dispositionLabel: string,
 *   legacyDisposition: boolean,
 *   reason: string
 * }} NormalizedUnknownSemantic
 * @typedef {{ review: NormalizedUnknownSemantic[], informational: NormalizedUnknownSemantic[] }} UnknownSemanticGroups
 */

/** @type {Readonly<Record<string, SemanticStatus>>} */
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

/** @param {unknown} value @returns {value is SemanticObject} */
function isSemanticObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** @param {unknown} value @returns {SemanticObject} */
function object(value) {
  return isSemanticObject(value) ? value : {};
}

/** @param {unknown} value @returns {unknown[]} */
function array(value) {
  return Array.isArray(value) ? value : [];
}

/** @param {unknown} value @returns {string[]} */
function stringArray(value) {
  return array(value)
    .filter((item) => item !== undefined && item !== null && item !== "")
    .map(String);
}

/** @param {unknown} value @returns {string} */
function stringValue(value) {
  return value === undefined || value === null ? "" : String(value);
}

/** @param {SemanticRecord} record @returns {SemanticObject} */
function classificationOf(record) {
  const source = object(record);
  return isSemanticObject(source.classification) ? source.classification : source;
}

/** @param {unknown} value @returns {SemanticStatus} */
function normalizedStatus(value) {
  const normalized = STATUS_ALIASES[stringValue(value).toUpperCase()];
  return normalized || "NO_CONFIRMED";
}

/** @param {RawFact | NormalizedFact} fact @returns {string} */
function directionOf(fact) {
  const source = object(fact);
  return String(
    source.evaluation_direction ?? source.sentiment ?? source.direction ?? "NEUTRAL",
  ).toUpperCase();
}

/** @param {RawFact | NormalizedFact} fact @returns {string} */
function assertionOf(fact) {
  const source = object(fact);
  return String(
    source.statement_type ??
      source.assertion_status ??
      source.assertion ??
      source.fact_type ??
      "AFFIRMED",
  ).toUpperCase();
}

/** @param {RawFact | NormalizedFact} fact @returns {boolean} */
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

/** @param {RawFact | NormalizedFact} fact @returns {string[]} */
function pathOf(fact) {
  const source = object(fact);
  const path =
    source.full_label_path ??
    source.label_path ??
    source.taxonomy_path ??
    source.labelPath ??
    [];
  if (Array.isArray(path)) return path.filter(Boolean).map(String);
  if (typeof path === "string") {
    return path
      .split(/\s*(?:→|>|\/|-)\s*/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
}

/** @param {unknown} value @returns {string} */
function conditionText(value) {
  if (!value) return "";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.filter(Boolean).join("、");
  if (typeof value === "object") {
    return Object.values(value).map(conditionText).filter(Boolean).join("；");
  }
  return String(value);
}

/** @param {...unknown} values @returns {unknown} */
function firstValue(...values) {
  return values.find(
    (value) => value !== undefined && value !== null && String(value).trim(),
  );
}

/** @param {...unknown} values @returns {string} */
function firstText(...values) {
  return stringValue(firstValue(...values));
}

/** @param {...unknown} values @returns {string} */
function coalescedText(...values) {
  return stringValue(values.find((value) => value !== undefined && value !== null));
}

/**
 * @param {RawFact | SemanticObject} fact
 * @param {number} index
 * @param {unknown} [scope]
 * @returns {NormalizedFact}
 */
function normalizedFact(fact, index, scope = {}) {
  const source = object(fact);
  const factScope = object(source.scope);
  const scopeSource = object(scope);
  const evidenceSpans = array(source.evidence_spans).map(object);
  return {
    ...source,
    factId: coalescedText(
      source.fact_id,
      array(source.fact_ids)[0],
      source.source_fact_id,
      source.id,
    ),
    labelCode: coalescedText(
      source.label_code,
      source.verdict_label_code,
      source.labelCode,
    ),
    labelPath: pathOf(source),
    opinion: firstText(
      source.opinion,
      source.fact_text_zh,
      source.fact_summary,
      source.summary,
    ),
    subject: firstText(source.subject, source.object_type, factScope.subject),
    direction: directionOf(fact),
    assertion: assertionOf(fact),
    sourceRef: firstText(
      scopeSource.source_ref,
      source.source_ref,
      factScope.source_ref,
      source.sourceRef,
    ),
    experiencerRef: firstText(
      scopeSource.experiencer_ref,
      scopeSource.actor_ref,
      source.experiencer_ref,
      source.actor_ref,
      source.actor,
      factScope.experiencer_ref,
      factScope.actor,
      source.experiencerRef,
    ),
    productRef: firstText(
      scopeSource.product_ref,
      source.product_ref,
      factScope.product_ref,
      source.productRef,
    ),
    variantRef: firstText(
      scopeSource.variant_ref,
      source.variant_ref,
      factScope.variant_ref,
      source.variantRef,
    ),
    eventRef: firstText(
      scopeSource.event_ref,
      source.event_ref,
      source.event_id,
      factScope.event_ref,
      source.eventRef,
    ),
    referenceBasis: firstText(
      scopeSource.reference_basis,
      source.reference_basis,
      factScope.reference_basis,
      source.referenceBasis,
    ),
    condition: conditionText(
      firstValue(
        scopeSource.condition,
        source.condition,
        source.conditions,
        factScope.condition,
      ),
    ),
    operation: firstText(scopeSource.operation, source.operation, factScope.operation),
    part: firstText(scopeSource.part, source.part, factScope.part),
    evidence: coalescedText(
      source.evidence,
      source.evidence_text,
      source.text,
      evidenceSpans
        .map((span) => span.text)
        .filter(Boolean)
        .join(" … "),
    ),
    evidenceSource: coalescedText(
      source.evidence_source,
      source.source,
      source.evidenceSource,
      evidenceSpans
        .map((span) => span.source)
        .filter(Boolean)
        .join("+"),
    ),
    decisionReason: firstText(
      source.decision_reason,
      source.verdict_reason,
      source.decisionReason,
    ),
    mappingReason: firstText(
      source.mapping_reason,
      source.mappingReason,
      source.reason,
    ),
    relationType: String(
      firstValue(
        source.relation_type,
        source.fact_relation_type,
        source.relationType,
      ) || "",
    ).toUpperCase(),
    relatedFactIds: stringArray(
      source.related_fact_ids ?? source.cause_fact_ids ?? source.relatedFactIds,
    ),
    causalAttribution: firstText(
      source.causal_attribution,
      source.cause_attribution,
      source.cause_actor,
      source.cause_ref,
      source.cause,
      source.causalAttribution,
    ),
    position: index,
  };
}

/**
 * @param {SemanticObject} classification
 * @param {SemanticObject} record
 * @returns {unknown[][]}
 */
function factSources(classification, record) {
  const candidates = [
    record.atomic_facts,
    record.semantic_units,
    classification.atomic_facts,
    classification.semantic_units,
    record.semantic_facts,
    classification.semantic_facts,
    record.extracted_facts,
    classification.extracted_facts,
    record.facts,
    classification.facts,
    record.evidence,
  ];
  /** @type {unknown[][]} */
  const sources = [];
  candidates.forEach((candidate) => {
    if (Array.isArray(candidate)) sources.push(candidate);
  });
  return sources;
}

/**
 * @param {SemanticObject} classification
 * @param {SemanticObject} record
 * @returns {SemanticObject[]}
 */
function mappingSources(classification, record) {
  return array(record.fact_mappings ?? classification.fact_mappings).filter(
    isSemanticObject,
  );
}

/** @param {unknown} value @returns {boolean} */
function meaningful(value) {
  return value !== undefined && value !== null && value !== "";
}

/**
 * @param {NormalizedFact} primary
 * @param {SemanticObject} secondary
 * @returns {NormalizedFact}
 */
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

/**
 * @param {SemanticObject} classification
 * @param {SemanticObject} record
 * @returns {NormalizedFact[]}
 */
function sourceFacts(classification, record) {
  /** @type {Map<string, NormalizedFact>} */
  const identified = new Map();
  /** @type {NormalizedFact[]} */
  const anonymous = [];
  const sources = factSources(classification, record);
  const primarySourceIndex = sources.findIndex((facts) => facts.length > 0);
  sources.forEach((facts, sourceIndex) => {
    facts.forEach((fact, index) => {
      const normalized = normalizedFact(object(fact), index);
      if (!normalized.factId) {
        if (sourceIndex === primarySourceIndex) anonymous.push(normalized);
        return;
      }
      const existing = identified.get(normalized.factId);
      identified.set(
        normalized.factId,
        existing ? mergeFacts(existing, normalized) : normalized,
      );
    });
  });
  const mappings = new Map(
    mappingSources(classification, record).map((mapping) => [
      stringValue(mapping.fact_id),
      mapping,
    ]),
  );
  return [...identified.values(), ...anonymous].map((fact) => {
    const mapping = mappings.get(fact.factId);
    if (!mapping) return fact;
    return mergeFacts(fact, {
      mappingReason: stringValue(mapping.reason),
      relationType: stringValue(mapping.relation_type),
      relatedFactIds: stringArray(mapping.related_fact_ids),
    });
  });
}

/**
 * @param {SemanticObject} classification
 * @param {SemanticObject} record
 * @returns {unknown[]}
 */
function conclusionSources(classification, record) {
  return array(
    record.comment_conclusions ??
      record.aspect_summaries ??
      record.semantic_summaries ??
      record.topic_summaries ??
      classification.comment_conclusions ??
      classification.aspect_summaries ??
      classification.semantic_summaries ??
      classification.topic_summaries ??
      [],
  );
}

/**
 * @param {SemanticObject} classification
 * @param {SemanticObject} record
 * @returns {unknown[]}
 */
function dimensionDecisionSources(classification, record) {
  return array(record.dimension_decisions ?? classification.dimension_decisions);
}

/** @param {NormalizedFact} fact @returns {string} */
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

/** @param {NormalizedFact[]} facts @returns {SemanticStatus} */
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

/** @param {NormalizedFact} fact @returns {SemanticTopic} */
function topicForFact(fact) {
  const explicit = coalescedText(
    fact.aspect_label ??
      fact.aspect_name ??
      fact.topic_label ??
      fact.aspect ??
      fact.topic,
  );
  if (explicit) {
    return {
      key: coalescedText(fact.aspect_code, fact.topic_code, explicit),
      label: explicit,
      path: stringArray(fact.aspect_path),
    };
  }
  const topicPath = fact.labelPath.length > 1 ? fact.labelPath.slice(0, -1) : [];
  return {
    key: topicPath.join("/") || fact.labelCode || "未归类主题",
    label: topicPath.at(-1) || fact.labelCode || "未归类主题",
    path: topicPath,
  };
}

/**
 * @param {NormalizedFact[]} facts
 * @param {boolean} [legacy]
 * @returns {SemanticConclusion[]}
 */
function deriveConclusions(facts, legacy = true) {
  /** @type {Map<string, SemanticTopic & { facts: NormalizedFact[] }>} */
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

/**
 * @param {unknown} conclusionValue
 * @param {number} index
 * @param {NormalizedFact[]} allFacts
 * @returns {SemanticConclusion}
 */
function normalizeConclusion(conclusionValue, index, allFacts) {
  const conclusion = object(conclusionValue);
  const factIds = stringArray(conclusion.supporting_fact_ids ?? conclusion.fact_ids);
  const labelCodes = stringArray(conclusion.label_codes);
  const embeddedFacts = array(conclusion.facts ?? conclusion.atomic_facts).map(
    (fact, factIndex) => normalizedFact(object(fact), factIndex),
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
      ...stringArray(conclusion.aspect_path),
      ...stringArray(conclusion.topic_path),
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
  const topicPath = stringArray(conclusion.aspect_path ?? conclusion.topic_path);
  return {
    id: coalescedText(
      conclusion.id,
      conclusion.aspect_code,
      conclusion.topic_code,
      `topic-${index}`,
    ),
    topic: coalescedText(
      conclusion.aspect_label,
      conclusion.aspect_name,
      conclusion.topic_label,
      conclusion.topic_name,
      conclusion.label,
      topicPath.at(-1),
      "未归类主题",
    ),
    topicPath,
    status: normalizedStatus(
      conclusion.summary_status ?? conclusion.status ?? conclusion.sentiment_status,
    ),
    summary: coalescedText(
      conclusion.summary,
      conclusion.statement,
      conclusion.conclusion,
    ),
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

/**
 * @param {unknown[]} decisions
 * @param {NormalizedFact[]} allFacts
 * @returns {{ conclusions: SemanticConclusion[], consumedFactIds: Set<string> }}
 */
function decisionConclusions(decisions, allFacts) {
  /**
   * @type {Map<string, {
   *   id: string,
   *   topic: string,
   *   topicPath: string[],
   *   summary: string,
   *   facts: NormalizedFact[],
   *   contextFacts: NormalizedFact[],
   *   reasons: string[],
   *   legacy: boolean
   * }>}
   */
  const groups = new Map();
  /** @type {Set<string>} */
  const consumedFactIds = new Set();
  decisions.forEach((decisionValue, index) => {
    const decision = object(decisionValue);
    const supportingIds = stringArray(decision.supporting_fact_ids);
    const contextIds = stringArray(decision.context_fact_ids);
    supportingIds.forEach((factId) => consumedFactIds.add(factId));
    contextIds.forEach((factId) => consumedFactIds.add(factId));
    const supportingFacts = supportingIds.map((factId) => {
      const matched = allFacts.find((fact) => fact.factId === factId) ?? {
        fact_id: factId,
      };
      return normalizedFact(
        {
          ...matched,
          label_code: stringValue(decision.verdict_label_code),
          decision_reason: stringValue(decision.reason),
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
    const verdictLabelCode = stringValue(decision.verdict_label_code);
    const verdictFact =
      supportingFacts.find((fact) => fact.labelCode === verdictLabelCode) ??
      allFacts.find((fact) => fact.labelCode === verdictLabelCode);
    const topic = topicForFact(
      verdictFact ?? supportingFacts[0] ?? normalizedFact({}, index),
    );
    const key = firstText(decision.parent_code, topic.key, `decision-${index}`);
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
    const reason = stringValue(decision.reason);
    if (reason) current.reasons.push(reason);
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

/** @param {SemanticRecord} record @returns {SemanticConclusion[]} */
export function semanticConclusions(record) {
  const source = object(record);
  const classification = classificationOf(record);
  const facts = sourceFacts(classification, source);
  const decisions = dimensionDecisionSources(classification, source);
  if (decisions.length) {
    const { conclusions, consumedFactIds } = decisionConclusions(decisions, facts);
    const residual = facts.filter(
      (fact) =>
        !consumedFactIds.has(fact.factId) && (fact.labelCode || fact.labelPath.length),
    );
    return [...conclusions, ...deriveConclusions(residual, false)];
  }
  const provided = conclusionSources(classification, source);
  return provided.length
    ? provided.map((conclusion, index) => normalizeConclusion(conclusion, index, facts))
    : deriveConclusions(facts);
}

/** @param {SemanticRecord} record @returns {SemanticStatus} */
export function semanticRecordStatus(record) {
  const source = object(record);
  const classification = classificationOf(record);
  const explicit =
    source.comment_summary_status ??
    object(source.comment_summary).status ??
    source.semantic_status ??
    classification.comment_summary_status ??
    object(classification.comment_summary).status ??
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

/** @param {SemanticRecord} record @returns {SemanticRelation[]} */
export function semanticRelations(record) {
  const source = object(record);
  const classification = classificationOf(record);
  const relations = source.semantic_relations ?? classification.semantic_relations;
  return array(relations).map((relationValue, index) => {
    const relation = object(relationValue);
    return {
      id: coalescedText(relation.id, `relation-${index}`),
      type: coalescedText(relation.relation_type, relation.type, "").toUpperCase(),
      reason: coalescedText(relation.reason, "未提供关系说明"),
      factIds: stringArray(relation.fact_ids),
    };
  });
}

/**
 * @param {RawUnknownSemantic | unknown} unknownValue
 * @param {number} index
 * @param {string} [fallbackDisposition]
 * @returns {NormalizedUnknownSemantic}
 */
function normalizeUnknown(unknownValue, index, fallbackDisposition = "") {
  const item =
    typeof unknownValue === "string"
      ? { opinion: unknownValue, evidence: unknownValue }
      : object(unknownValue);
  const normalized = normalizedFact(item, index);
  const disposition = firstText(item.disposition, fallbackDisposition).toUpperCase();
  return {
    ...normalized,
    id: normalized.factId || `unknown-${index}`,
    opinion: coalescedText(item.opinion, item.text, ""),
    reason: coalescedText(item.reason, ""),
    disposition,
    dispositionLabel: disposition
      ? DISPOSITION_LABELS[disposition] || disposition
      : "旧结果未提供处置",
    legacyDisposition: !disposition,
  };
}

/** @param {NormalizedUnknownSemantic} item @returns {string} */
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

/** @param {SemanticRecord} record @returns {UnknownSemanticGroups} */
export function semanticUnknownGroups(record) {
  const source = object(record);
  const classification = classificationOf(record);
  /** @type {Array<[unknown, string]>} */
  const sources = [];
  array(source.unknown_semantics).forEach((item) => sources.push([item, ""]));
  array(classification.unknown_semantics).forEach((item) => sources.push([item, ""]));
  array(source.ignored_semantics).forEach((item) =>
    sources.push([item, "EXPECTED_ABSTENTION"]),
  );
  array(classification.ignored_semantics).forEach((item) =>
    sources.push([item, "EXPECTED_ABSTENTION"]),
  );
  /** @type {Set<string>} */
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
  /** @type {UnknownSemanticGroups} */
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

/** @param {unknown} status @returns {string} */
export function semanticStatusLabel(status) {
  return SEMANTIC_STATUS_LABELS[normalizedStatus(status)];
}

/** @param {string} value @returns {string} */
function participantLabel(value) {
  return PARTICIPANT_LABELS[value] || value;
}

/** @param {RawFact | NormalizedFact} fact @returns {PresentedFact} */
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
