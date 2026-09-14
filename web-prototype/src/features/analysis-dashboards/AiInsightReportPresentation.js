export const STATUS_LABELS = {
  queued: "等待生成",
  running: "正在生成",
  completed: "生成完成",
  failed: "生成失败",
};

export const QUALITY_GATE_LABELS = {
  passed: "质量通过",
  warning: "质量警告",
  blocked: "质量阻断",
};

export const STAGE_LABELS = {
  queued: "等待生成",
  preparing_evidence: "正在准备确定性证据",
  calling_model: "模型正在解释证据",
  assembling_report: "正在装配报告",
  publishing: "正在发布报告",
};

export function reportLabel(report) {
  return report.version_no
    ? `报告 V${report.version_no}`
    : `生成尝试 ${report.attempt_no ?? "-"}`;
}

export function number(value) {
  return Number(value || 0);
}

export function percent(value) {
  return `${number(value).toFixed(1)}%`;
}

export function date(value) {
  return value ? String(value).slice(0, 10).replaceAll("-", "/") : "未提供";
}

export function shortDate(value) {
  const text = date(value);
  return text === "未提供" ? text : text.slice(5);
}

export function evidenceItems(ids, catalog) {
  return (ids ?? []).map((id) => catalog[id]).filter(Boolean);
}

export function diagnosticMap(analysis) {
  return new Map(
    (analysis.diagnostics ?? []).map((item) => [String(item.reason_code), item]),
  );
}

export function findingReasonCode(finding) {
  const reasonId = (finding?.evidence_ids ?? []).find((item) =>
    String(item).startsWith("reason."),
  );
  return reasonId ? String(reasonId).slice("reason.".length) : "";
}

export function mergeSizeTrend(diagnostics, dateTo) {
  const rows = new Map();
  const append = (code, field) => {
    const diagnostic = diagnostics.get(code);
    for (const item of diagnostic?.trend ?? []) {
      if (item.low_sample || (dateTo && item.period_end > dateTo)) continue;
      const row = rows.get(item.period_start) ?? {
        period_start: item.period_start,
        period_end: item.period_end,
        total_record_count: item.total_record_count,
      };
      row[field] = number(item.percentage);
      rows.set(item.period_start, row);
    }
  };
  append("FIT_TOO_SMALL", "too_small");
  append("FIT_TOO_LARGE", "too_large");
  return [...rows.values()]
    .filter((item) => item.too_small !== undefined || item.too_large !== undefined)
    .sort((left, right) => String(left.period_start).localeCompare(right.period_start));
}

export function hotspotGroups(diagnostics) {
  const groups = [];
  for (const code of ["FIT_TOO_SMALL", "FIT_TOO_LARGE"]) {
    const diagnostic = diagnostics.get(code);
    const label = diagnostic?.selected_reason?.label || code;
    const rows = [...(diagnostic?.hotspots ?? [])]
      .sort(
        (left, right) =>
          number(right.excess_record_count) - number(left.excess_record_count) ||
          number(right.lift) - number(left.lift),
      )
      .slice(0, 3);
    if (rows.length) groups.push({ code, label, rows });
  }
  return groups;
}

export function signedPercentagePoints(value) {
  const numericValue = number(value);
  return `${numericValue > 0 ? "+" : ""}${numericValue.toFixed(1)}pp`;
}

export function reasonSamples(diagnostic) {
  return (diagnostic?.samples ?? []).filter(
    (item, index, items) =>
      index ===
      items.findIndex(
        (candidate) =>
          (candidate.comment || candidate.reason) === (item.comment || item.reason),
      ),
  );
}
