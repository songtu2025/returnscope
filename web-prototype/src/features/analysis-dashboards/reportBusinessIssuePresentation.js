import { analysisContextTerms } from "./analysisContextPresentation";
import { number } from "./AiInsightReportPresentation";
/** @typedef {import("./analysisDashboardContracts").ReportBusinessIssue} ReportBusinessIssue */
/** @param {ReportBusinessIssue} issue @param {string} analysisContext */
export function businessIssueView(issue, analysisContext) {
  const terms = analysisContextTerms(analysisContext);
  const hotspots = issue.hotspots ?? [];
  const leadHotspot = hotspots[0];
  const trend = issue.trend_summary ?? {};
  const contexts = issue.contexts ?? {};
  const parts = (contexts.parts ?? []).filter(
    (item) => !["UNSPECIFIED", "整体", "未说明"].includes(String(item.value)),
  );
  const opinions = contexts.opinions ?? [];
  const samples = contexts.samples ?? [];
  const baseline = number(leadHotspot?.overall_reason_rate);
  const leadRate = number(leadHotspot?.product_reason_rate);

  return {
    terms,
    hotspots,
    leadHotspot,
    trend,
    parts,
    opinions,
    samples,
    baseline,
    leadRate,
  };
}
