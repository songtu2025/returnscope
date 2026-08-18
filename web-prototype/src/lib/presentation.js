export function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(date);
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
