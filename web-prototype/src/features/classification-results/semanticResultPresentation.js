import {
  object,
  array,
  stringArray,
  classificationOf,
  firstText,
  coalescedText,
  normalizedFact,
} from "./semanticResultFacts";

export { semanticConclusions } from "./semanticConclusionProjection";
export {
  SEMANTIC_STATUS_LABELS,
  semanticRecordStatus,
  semanticStatusLabel,
} from "./semanticStatusPresentation";

/**
 * @typedef {import("./semanticResultFacts").SemanticObject} SemanticObject
 * @typedef {import("./semanticResultFacts").SemanticRecord} SemanticRecord
 * @typedef {import("./semanticResultFacts").RawFact} RawFact
 * @typedef {import("./semanticResultFacts").NormalizedFact} NormalizedFact
 * @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationUnknownSemanticResponse} GeneratedUnknownSemantic
 * @typedef {GeneratedUnknownSemantic | SemanticObject | string} RawUnknownSemantic
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
    } else {
      groups.review.push(item);
    }
  });
  return groups;
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
