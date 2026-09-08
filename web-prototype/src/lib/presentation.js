function padDatePart(value) {
  return String(value).padStart(2, "0");
}

function parseDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatLocalDate(date) {
  return `${date.getFullYear()}-${padDatePart(date.getMonth() + 1)}-${padDatePart(date.getDate())}`;
}

export function formatDate(value) {
  if (!value) return "—";
  const date = parseDate(value);
  return date ? formatLocalDate(date) : value;
}

export function formatTime(value) {
  if (!value) return "—";
  const date = parseDate(value);
  return date
    ? `${formatLocalDate(date)} ${padDatePart(date.getHours())}:${padDatePart(date.getMinutes())}`
    : value;
}

export function classNames(...values) {
  return values.filter(Boolean).join(" ");
}

export function formatNumber(value) {
  return Number(value ?? 0).toLocaleString("zh-CN");
}

export function formatPercent(value, digits = 1) {
  return `${(Number(value ?? 0) * 100).toFixed(digits)}%`;
}
