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

const PART_LABELS = {
  WHOLE_SHOE: "整鞋",
  TOE: "鞋头",
  OPENING: "鞋口",
  OUTSOLE: "外底",
  INSOLE: "鞋垫",
  UPPER: "鞋面",
  HEEL: "后跟",
  HEEL_TAB: "后跟提拉片",
  SOLE_UPPER_SEAM: "鞋底与鞋面结合处",
  ARCH: "足弓",
  INSTEP: "脚背部位",
  SEAM: "接缝",
  DRAINAGE_HOLE: "排水孔",
  FASTENER: "扣件",
  CUFF: "袖口",
  PALM: "掌心",
  BACK_OF_HAND: "手背",
  FINGER: "手指",
  FINGER_GUSSET: "指缝",
  THUMB: "拇指",
  THUMB_WEB: "虎口",
  LINING: "内衬",
  CLOSURE: "闭合结构",
  FRAME: "镜框",
  LENS: "镜片",
  NOSE_PAD: "鼻托",
  NOSE_BRIDGE: "鼻梁",
  TEMPLE: "镜腿",
  EAR_SIDE: "耳侧",
  HINGE: "铰链",
  SCREW: "螺丝",
  FACE_COVERAGE: "脸部覆盖",
  LENS_FRAME_JOINT: "镜片与镜框连接处",
  STRAP: "绑带",
  COATING: "镀膜",
  RUBBER_SLEEVE: "橡胶套",
  CASE: "眼镜盒",
  CLEANING_CLOTH: "清洁布",
  PACKAGING: "包装",
  EDGE: "边缘",
  CONNECTION: "连接处",
  ACCESSORY: "配件",
  CROWN: "帽身",
  BRIM: "帽檐",
  CHIN_STRAP: "下巴带",
  SIZE_ADJUSTER: "调节扣",
  UNSPECIFIED: "未明确部位",
};

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

/** @param {unknown} value */
export function partLabel(value) {
  const key = String(value || "");
  return (
    /** @type {Record<string, string>} */ (PART_LABELS)[key] ||
    String(value || "未明确部位").replaceAll("_", " ")
  );
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
