import { formatDate } from "../../lib/presentation";

export function datePresets() {
  const today = formatDate(new Date());
  const [year, month, day] = today.split("-").map(Number);
  // 先取北京时间的今天，再用 UTC 日历运算保留业务筛选的纯日期。
  /** @param {number} monthNumber @param {number} dayNumber */
  const date = (monthNumber, dayNumber) =>
    new Date(Date.UTC(year, monthNumber - 1, dayNumber)).toISOString().slice(0, 10);

  return [
    { label: "不限日期", date_from: "", date_to: "" },
    {
      label: "近7天",
      date_from: date(month, day - 6),
      date_to: today,
    },
    {
      label: "近30天",
      date_from: date(month, day - 29),
      date_to: today,
    },
    {
      label: "本月至今",
      date_from: date(month, 1),
      date_to: today,
    },
    {
      label: "上月",
      date_from: date(month - 1, 1),
      date_to: date(month, 0),
    },
  ];
}
