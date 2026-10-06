import { object, stringValue } from "./semanticResultFacts";

/** @typedef {"POSITIVE" | "NEGATIVE" | "MIXED" | "CONFLICT" | "NO_CONFIRMED"} SemanticStatus */
/** @typedef {import("./semanticResultFacts").SemanticRecord} SemanticRecord */

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

/** @param {unknown} value @returns {SemanticStatus} */
export function normalizedStatus(value) {
  const normalized = STATUS_ALIASES[stringValue(value).toUpperCase()];
  return normalized || "NO_CONFIRMED";
}

/** @param {SemanticRecord} record @returns {SemanticStatus} */
export function semanticRecordStatus(record) {
  return normalizedStatus(object(record).comment_summary_status);
}

/** @param {unknown} status @returns {string} */
export function semanticStatusLabel(status) {
  return SEMANTIC_STATUS_LABELS[normalizedStatus(status)];
}
