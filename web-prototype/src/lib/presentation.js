const PURE_DATE = /^\d{4}-\d{2}-\d{2}$/;
const UTC_WITHOUT_OFFSET = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/;
const systemTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** @param {unknown} value */
function parseDate(value) {
  if (value == null || value === "") return null;
  const date =
    value instanceof Date
      ? new Date(value)
      : typeof value === "number"
        ? new Date(value)
        : new Date(
            UTC_WITHOUT_OFFSET.test(String(value))
              ? // 后端无偏移的系统时间戳按 UTC 解释，显示始终使用北京时间。
                String(value).replace(" ", "T") + "Z"
              : String(value),
          );
  return Number.isNaN(date.getTime()) ? null : date;
}

/** @param {Date} date */
function systemTimeParts(date) {
  const parts = Object.fromEntries(
    systemTimeFormatter.formatToParts(date).map(({ type, value }) => [type, value]),
  );
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    time: `${parts.hour}:${parts.minute}`,
  };
}

/** @param {unknown} value */
export function formatDate(value) {
  if (value == null || value === "") return "--";
  if (typeof value === "string" && PURE_DATE.test(value)) return value;
  const date = parseDate(value);
  return date ? systemTimeParts(date).date : String(value);
}

/** @param {unknown} value */
export function formatTime(value) {
  if (value == null || value === "") return "--";
  if (typeof value === "string" && PURE_DATE.test(value)) return value;
  const date = parseDate(value);
  if (!date) return String(value);
  const parts = systemTimeParts(date);
  return `${parts.date} ${parts.time}`;
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
