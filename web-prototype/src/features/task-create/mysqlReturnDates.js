export function datePresets() {
  const today = new Date();
  const year = today.getFullYear();
  const month = today.getMonth();
  const day = today.getDate();
  /** @param {Date | null} date */
  const format = (date) =>
    date
      ? `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`
      : "";

  return [
    { label: "不限日期", date_from: "", date_to: "" },
    {
      label: "近7天",
      date_from: format(new Date(year, month, day - 6)),
      date_to: format(today),
    },
    {
      label: "近30天",
      date_from: format(new Date(year, month, day - 29)),
      date_to: format(today),
    },
    {
      label: "本月至今",
      date_from: format(new Date(year, month, 1)),
      date_to: format(today),
    },
    {
      label: "上月",
      date_from: format(new Date(year, month - 1, 1)),
      date_to: format(new Date(year, month, 0)),
    },
  ];
}
