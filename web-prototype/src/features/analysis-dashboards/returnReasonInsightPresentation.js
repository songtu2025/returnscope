import { groups as BUSINESS_GROUPS } from "../../../../config/taxonomy_alignment.json";

const GROUP_ORDER = [
  ...new Set([
    ...BUSINESS_GROUPS,
    "尺码与适配",
    "尺码与合脚",
    "功能表现",
    "功能",
    "质量与耐用性",
    "穿戴体验",
    "体感",
    "外观",
    "其他原因",
  ]),
];

export { partLabel } from "../../lib/semanticParts";

export const COMMENT_STATUS_ORDER = [
  "POSITIVE",
  "NEGATIVE",
  "MIXED",
  "CONFLICT",
  "NO_CONFIRMED",
];

/** @param {unknown} value */
export function formatPercent(value) {
  return `${Number(value || 0).toFixed(1)}%`;
}

/** @param {unknown} value */
export function formatDate(value) {
  if (!value) return "未提供";
  return String(value).slice(0, 10);
}

/** @param {unknown} value */
export function shortDate(value) {
  const text = formatDate(value);
  return text === "未提供" ? text : text.slice(5).replace("-", "/");
}

/** @template T @param {T[] | null | undefined} values @returns {T[]} */
export function filterOptions(values) {
  return Array.isArray(values) ? values : [];
}

/** @typedef {{label_code?: string, opinion?: string, part?: string} & Record<string, unknown>} ReturnSemanticUnit */
/** @param {{classification?: {semantic_units?: ReturnSemanticUnit[]}}} record @param {string} labelCode @returns {ReturnSemanticUnit} */
export function selectedSemanticUnit(record, labelCode) {
  const units = record.classification?.semantic_units ?? [];
  return units.find((unit) => unit.label_code === labelCode) ?? units[0] ?? {};
}

/** @typedef {{status?: string, summary_status?: string, comment_count?: number, record_count?: number, count?: number}} CommentStatusRow */
/** @typedef {{comment_statuses?: CommentStatusRow[] | Record<string, number>, semantic_statuses?: CommentStatusRow[] | Record<string, number>}} CommentStatusSource */
/** @param {CommentStatusSource} data @param {CommentStatusSource} summary @returns {Record<string, number> | null} */
export function commentStatusCounts(data, summary) {
  const raw =
    summary.comment_statuses ??
    summary.semantic_statuses ??
    data.comment_statuses ??
    data.semantic_statuses;
  if (!raw) return null;
  if (!Array.isArray(raw)) return raw;
  return Object.fromEntries(
    raw.map((item) => [
      String(item.status ?? item.summary_status ?? "").toUpperCase(),
      Number(item.comment_count ?? item.record_count ?? item.count ?? 0),
    ]),
  );
}

/** @param {string[]} categoryGroups */
export function orderGroups(categoryGroups) {
  return [
    ...GROUP_ORDER.filter((item) => categoryGroups.includes(item)),
    ...categoryGroups.filter((item) => !GROUP_ORDER.includes(item)),
  ];
}
