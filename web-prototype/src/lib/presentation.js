/** @param {string | number} value */
function padDatePart(value) {
  return String(value).padStart(2, "0");
}

/** @param {unknown} value */
function parseDate(value) {
  if (!value) return null;
  const date =
    value instanceof Date
      ? new Date(value)
      : typeof value === "number"
        ? new Date(value)
        : new Date(String(value));
  return Number.isNaN(date.getTime()) ? null : date;
}

/** @param {Date} date */
function formatLocalDate(date) {
  return `${date.getFullYear()}-${padDatePart(date.getMonth() + 1)}-${padDatePart(date.getDate())}`;
}

/** @param {unknown} value */
export function formatDate(value) {
  if (!value) return "—";
  const date = parseDate(value);
  return date ? formatLocalDate(date) : String(value);
}

/** @param {unknown} value */
export function formatTime(value) {
  if (!value) return "—";
  const date = parseDate(value);
  return date
    ? `${formatLocalDate(date)} ${padDatePart(date.getHours())}:${padDatePart(date.getMinutes())}`
    : String(value);
}

/** @param {...unknown} values */
export function classNames(...values) {
  return values.filter(Boolean).join(" ");
}

/** @param {unknown} value */
export function formatNumber(value) {
  return Number(value ?? 0).toLocaleString("zh-CN");
}

/** @param {unknown} value @param {number} [digits] */
export function formatPercent(value, digits = 1) {
  return `${(Number(value ?? 0) * 100).toFixed(digits)}%`;
}
