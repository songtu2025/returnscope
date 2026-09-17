import {
  semanticConclusions,
  semanticUnknownGroups,
} from "../classification-results/semanticResultPresentation";

const REVIEW_DISPOSITIONS = new Set([
  "ANALYSIS_FAILURE",
  "MODEL_ERROR",
  "MAPPING_UNCERTAIN",
  "TAXONOMY_GAP",
  "TRUE_AMBIGUITY",
  "UNKNOWN",
]);

const INFORMATIONAL_DISPOSITIONS = new Set([
  "EXPECTED_ABSTENTION",
  "NO_TAG_NEEDED",
  "OUT_OF_SCOPE",
]);

/** @typedef {Record<string, any>} SemanticData */

/** @type {Record<string, string>} */
export const REVIEW_DISPOSITION_LABELS = {
  MAPPED: "已归类",
  EXPECTED_ABSTENTION: "按规则无需归类",
  NO_TAG_NEEDED: "无需归类",
  OUT_OF_SCOPE: "当前范围外",
  TAXONOMY_GAP: "标签体系缺口",
  MAPPING_UNCERTAIN: "标签待判断",
  TRUE_AMBIGUITY: "原文含义不明确",
  ANALYSIS_FAILURE: "系统处理失败",
  MODEL_ERROR: "系统处理失败",
  UNKNOWN: "待判断",
  UNEXPLAINED: "未解释原文片段",
};

/** @param {any} value @returns {any[]} */
function array(value) {
  return Array.isArray(value) ? value : [];
}

/** @param {SemanticData} item @param {string} [fallback] */
function normalizeDisposition(item, fallback = "") {
  const explicit = String(item.disposition || item.status || fallback).toUpperCase();
  if (explicit) return explicit;
  return item.label_code || item.labelCode ? "MAPPED" : "UNKNOWN";
}

/** @param {SemanticData} item @param {number} index @param {string} [fallbackDisposition] */
function normalizeItem(item, index, fallbackDisposition = "") {
  const evidenceSpans = array(item.evidence_spans);
  const labelPath = array(item.label_path ?? item.taxonomy_path ?? item.labelPath);
  return {
    ...item,
    id:
      item.semantic_item_id ||
      item.item_id ||
      item.fact_id ||
      item.factId ||
      item.id ||
      `semantic-item-${index}`,
    evidence:
      item.evidence_text ||
      item.evidence ||
      evidenceSpans
        .map((span) => span?.text)
        .filter(Boolean)
        .join(" … ") ||
      "无文本证据",
    evidenceSource:
      item.evidence_source ||
      item.evidenceSource ||
      evidenceSpans
        .map((span) => span?.source)
        .filter(Boolean)
        .join("+") ||
      "",
    opinion:
      item.opinion ||
      item.fact_text_zh ||
      item.fact_summary ||
      item.summary ||
      "旧结果未提供独立观点",
    labelCode: item.label_code || item.labelCode || "",
    labelPath,
    disposition: normalizeDisposition(item, fallbackDisposition),
    reason: item.reason || item.mapping_reason || item.mappingReason || "",
    diagnosticDomain: item.diagnostic_domain || item.diagnosticDomain || "",
    diagnosticCode: item.diagnostic_code || item.diagnosticCode || item.code || "",
    diagnosticTitle: item.diagnostic_title || item.diagnosticTitle || item.title || "",
    detailStatus: item.detail_status || item.detailStatus || "",
    primaryResult: item.primary_result || item.primaryResult || "",
    secondaryResult: item.secondary_result || item.secondaryResult || "",
    diagnosticDetail: item.detail || item.diagnosticDetail || "",
    diagnosticAction: item.action || item.diagnosticAction || "",
    businessReviewRequired:
      item.business_review_required ?? item.businessReviewRequired,
    manual: Boolean(item.manual),
  };
}

/** @param {SemanticData} record */
function suppliedItems(record) {
  const classification = record?.classification ?? {};
  return (
    record?.semantic_review?.semantic_items ??
    classification.semantic_review?.semantic_items ??
    record?.semantic_review_items ??
    classification.semantic_review_items
  );
}

/** @param {SemanticData} record */
function suppliedReview(record) {
  const classification = record?.classification ?? {};
  return record?.semantic_review ?? classification.semantic_review ?? {};
}

/** @param {SemanticData} record @param {number} startIndex */
function unexplainedItems(record, startIndex) {
  return array(suppliedReview(record).unexplained_fragments).map((fragment, index) =>
    normalizeItem(
      {
        semantic_item_id: `unexplained-${index}`,
        evidence_text: String(fragment),
        opinion: "原文片段尚未获得语义处置",
        disposition: "UNEXPLAINED",
        reason: "请判断该片段是否需要归类",
      },
      startIndex + index,
    ),
  );
}

/** @param {SemanticData} record */
function suppliedSummary(record) {
  const summary = suppliedReview(record).coverage_summary;
  if (!summary || typeof summary !== "object") return null;
  return {
    mapped: Number(summary.mapped || 0),
    informational: Number(summary.no_tag_needed || 0),
    needsReview:
      Number(summary.taxonomy_gap || 0) +
      Number(summary.true_ambiguity || 0) +
      Number(summary.unexplained_fragment_count || 0),
    failures: Number(summary.analysis_failure || 0),
  };
}

/** @param {SemanticData} record */
function derivedItems(record) {
  const conclusions = semanticConclusions(record);
  const mapped = conclusions.flatMap((conclusion) => conclusion.facts ?? []);
  const unknowns = semanticUnknownGroups(record);
  return [
    ...mapped.map((item, index) => normalizeItem(item, index, "MAPPED")),
    ...unknowns.review.map((item, index) =>
      normalizeItem(item, mapped.length + index, item.disposition),
    ),
    ...unknowns.informational.map((item, index) =>
      normalizeItem(
        item,
        mapped.length + unknowns.review.length + index,
        item.disposition,
      ),
    ),
  ];
}

/** @param {SemanticData} record */
function legacyLabelItems(record) {
  const classification = record?.classification ?? {};
  const codes = array(
    classification.problem_label_codes ?? classification.primary_label_codes,
  );
  return codes.map((labelCode, index) =>
    normalizeItem(
      {
        semantic_item_id: `legacy-label-${index}`,
        evidence_text: record?.comment,
        label_code: labelCode,
      },
      index,
      "MAPPED",
    ),
  );
}

/** @param {SemanticData} item */
function priority(item) {
  if (
    ["ANALYSIS_FAILURE", "MODEL_ERROR"].includes(item.disposition) &&
    item.businessReviewRequired !== true
  ) {
    return 0;
  }
  if (item.disposition === "UNEXPLAINED") return 1;
  if (REVIEW_DISPOSITIONS.has(item.disposition)) return 1;
  if (INFORMATIONAL_DISPOSITIONS.has(item.disposition)) return 3;
  return 2;
}

/** @param {string} disposition @param {boolean | undefined} businessReviewRequired */
export function dispositionTone(disposition, businessReviewRequired) {
  if (["ANALYSIS_FAILURE", "MODEL_ERROR"].includes(disposition)) {
    return businessReviewRequired === true ? "review" : "failure";
  }
  if (disposition === "UNEXPLAINED") return "review";
  if (REVIEW_DISPOSITIONS.has(disposition)) return "review";
  if (INFORMATIONAL_DISPOSITIONS.has(disposition)) return "informational";
  return "mapped";
}

/** @param {SemanticData} item @param {SemanticData | null | undefined} review */
export function effectiveReviewItem(item, review) {
  if (!review || item.businessReviewRequired === false) return item;
  if (review.action === "change_label") {
    return {
      ...item,
      labelCode: review.label_code || item.labelCode,
      labelPath: [],
      disposition: "MAPPED",
    };
  }
  if (review.action === "no_tag_needed") {
    return { ...item, labelCode: "", labelPath: [], disposition: "NO_TAG_NEEDED" };
  }
  return item;
}

/** @param {SemanticData} record 将新旧语义结果统一为证据—观点—标签核验清单。 */
export function semanticReviewLedger(record) {
  const classification = record?.classification ?? {};
  const supplied = suppliedItems(record);
  let items = Array.isArray(supplied)
    ? supplied.map((item, index) => normalizeItem(item, index))
    : derivedItems(record);
  if (!items.length) items = legacyLabelItems(record);
  items = [...items, ...unexplainedItems(record, items.length)];

  const reviews = new Map(
    array(classification.human_semantic_reviews).map((review) => [
      review.semantic_item_id,
      review,
    ]),
  );
  const reviewedItems = items.map((item) => ({
    ...item,
    review: reviews.get(item.id) ?? null,
  }));
  const added = array(classification.human_added_semantic_items).map((item, index) => ({
    ...normalizeItem({ ...item, manual: true }, items.length + index, "MAPPED"),
    review: null,
  }));
  const sorted = [...reviewedItems, ...added].sort(
    (left, right) => priority(left) - priority(right),
  );

  return {
    items: sorted,
    summary: {
      mapped: sorted.filter((item) => item.disposition === "MAPPED").length,
      informational: sorted.filter((item) =>
        INFORMATIONAL_DISPOSITIONS.has(item.disposition),
      ).length,
      needsReview: sorted.filter(
        (item) =>
          (REVIEW_DISPOSITIONS.has(item.disposition) &&
            !["ANALYSIS_FAILURE", "MODEL_ERROR"].includes(item.disposition)) ||
          (["ANALYSIS_FAILURE", "MODEL_ERROR"].includes(item.disposition) &&
            item.businessReviewRequired === true),
      ).length,
      failures: sorted.filter(
        (item) =>
          ["ANALYSIS_FAILURE", "MODEL_ERROR"].includes(item.disposition) &&
          item.businessReviewRequired !== true,
      ).length,
    },
    coverageStatus: classification.coverage_review?.status || "complete",
    suppliedSummary: sorted.some(
      (item) => typeof item.businessReviewRequired === "boolean",
    )
      ? null
      : suppliedSummary(record),
  };
}
