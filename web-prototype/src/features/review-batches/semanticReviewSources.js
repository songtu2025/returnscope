import {
  semanticConclusions,
  semanticUnknownGroups,
} from "../classification-results/semanticResultPresentation";
import { dispositionTone } from "./semanticReviewPolicy";

/**
 * @typedef {import("../../shared/api/reviewBatchContracts").ReviewRecord} ReviewRecord
 * @typedef {import("../../shared/api/reviewBatchContracts").SemanticReviewData} SemanticReviewData
 * @typedef {import("../../shared/api/reviewBatchContracts").SemanticReviewLedgerItem} SemanticReviewLedgerItem
 * @typedef {import("../../shared/api/reviewBatchContracts").SemanticReviewSourceItem} SemanticReviewSourceItem
 */

/** @param {SemanticReviewSourceItem} item @param {string} [fallback] */
function normalizeDisposition(item, fallback = "") {
  const explicit = String(item.disposition || item.status || fallback).toUpperCase();
  // 业务诊断进入待判断清单；旧诊断没有明确标记时仍按系统异常展示。
  if (
    (item.business_review_required ?? item.businessReviewRequired) === true &&
    dispositionTone(explicit) === "failure"
  ) {
    return "UNKNOWN";
  }
  if (explicit) return explicit;
  return item.label_code || item.labelCode ? "MAPPED" : "UNKNOWN";
}

/** @param {SemanticReviewSourceItem} item */
function diagnosticFields(item) {
  return {
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
  };
}

/** @param {SemanticReviewSourceItem} item @param {number} index @param {string} [fallbackDisposition] @returns {SemanticReviewLedgerItem} */
export function normalizeItem(item, index, fallbackDisposition = "") {
  const evidenceSpans = item.evidence_spans ?? [];
  const labelPath = item.label_path ?? item.taxonomy_path ?? item.labelPath ?? [];
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
    ...diagnosticFields(item),
    manual: Boolean(item.manual),
    sentiment: item.sentiment || "",
  };
}

/** @param {ReviewRecord} record @returns {SemanticReviewData} */
function suppliedReview(record) {
  const classification = record?.classification ?? {};
  return record?.semantic_review ?? classification.semantic_review ?? {};
}

/** @param {ReviewRecord} record @returns {SemanticReviewSourceItem[] | undefined} */
export function suppliedItems(record) {
  const classification = record?.classification ?? {};
  return (
    suppliedReview(record).semantic_items ??
    record?.semantic_review_items ??
    classification.semantic_review_items
  );
}

/** @param {ReviewRecord} record @param {number} startIndex */
export function unexplainedItems(record, startIndex) {
  return (suppliedReview(record).unexplained_fragments ?? []).map((fragment, index) =>
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

/** @param {ReviewRecord} record @returns {import("../../shared/api/reviewBatchContracts").SemanticReviewSummary | null} */
export function suppliedSummary(record) {
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

/** @param {ReviewRecord} record @returns {SemanticReviewLedgerItem[]} */
export function derivedItems(record) {
  const conclusions = semanticConclusions(record);
  const mapped = conclusions.flatMap((conclusion) => conclusion.facts ?? []);
  const unknowns = semanticUnknownGroups(record);
  return [
    ...mapped.map((item, index) =>
      normalizeItem(/** @type {SemanticReviewSourceItem} */ (item), index, "MAPPED"),
    ),
    ...unknowns.review.map((item, index) =>
      normalizeItem(
        /** @type {SemanticReviewSourceItem} */ (item),
        mapped.length + index,
        item.disposition,
      ),
    ),
    ...unknowns.informational.map((item, index) =>
      normalizeItem(
        /** @type {SemanticReviewSourceItem} */ (item),
        mapped.length + unknowns.review.length + index,
        item.disposition,
      ),
    ),
  ];
}

/** @param {ReviewRecord} record @returns {SemanticReviewLedgerItem[]} */
export function legacyLabelItems(record) {
  const classification = record?.classification ?? {};
  const codes =
    classification.problem_label_codes ?? classification.primary_label_codes ?? [];
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

/** @param {SemanticReviewLedgerItem[]} items @param {NonNullable<ReviewRecord["classification"]>} classification */
export function reviewedLedgerItems(items, classification) {
  const reviews = new Map(
    (classification.human_semantic_reviews ?? []).map((review) => [
      review.applied ? review.result_item_id : review.semantic_item_id,
      review,
    ]),
  );
  return items.map((item) => ({
    ...item,
    review: reviews.get(item.id) ?? null,
    manual: (classification.human_added_semantic_items ?? []).some(
      (added) => added.applied && added.result_item_id === item.id,
    ),
    applied: true,
  }));
}
