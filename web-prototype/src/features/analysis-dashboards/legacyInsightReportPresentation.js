import {
  diagnosticMap,
  findingReasonCode,
  hotspotGroups,
  mergeSizeTrend,
  number,
  reasonSamples,
} from "./AiInsightReportPresentation";

/** @typedef {import("./analysisDashboardContracts").InsightReport} InsightReport */
/** @typedef {import("./analysisDashboardContracts").InsightReportAnalysis} InsightReportAnalysis */
/** @typedef {import("./analysisDashboardContracts").InsightReportSource} InsightReportSource */
/** @typedef {import("./analysisDashboardContracts").InsightEvidenceCatalog} InsightEvidenceCatalog */
/** @typedef {import("./analysisDashboardContracts").LegacyInsightReportContent} LegacyInsightReportContent */
/** @typedef {ReturnType<typeof diagnosticMap>} Diagnostics */

/** @param {LegacyInsightReportContent} content */
function reportFindings(content) {
  const findings = content.findings ?? [];
  const structureFinding =
    findings.find((item) => item.kind === "structure") ?? findings[0];
  const diagnosticFinding = findings.find((item) => item.kind === "diagnostic");
  const informationFinding = findings.find((item) => item.kind === "information");
  const otherFindings = findings.filter(
    (item) =>
      item !== structureFinding &&
      item !== diagnosticFinding &&
      item !== informationFinding,
  );
  return { structureFinding, diagnosticFinding, informationFinding, otherFindings };
}
/** @typedef {ReturnType<typeof reportFindings>} ReportFindings */

/** @param {InsightReportAnalysis} analysis @param {ReportFindings} findings @param {InsightEvidenceCatalog} catalog */
function structureSection(analysis, findings, catalog) {
  const groups = analysis.label_group_breakdown ?? [];
  const primaryGroup = groups.find((item) => item.value !== "其他原因") ?? groups[0];
  const maxGroupCount = Math.max(...groups.map((item) => number(item.record_count)), 1);
  return {
    structureFinding: findings.structureFinding,
    groups,
    primaryGroup,
    maxGroupCount,
    catalog,
  };
}

/** @param {InsightReportAnalysis} analysis @param {InsightReportSource} source @param {Diagnostics} diagnostics @param {ReportFindings} findings @param {InsightEvidenceCatalog} catalog */
function diagnosticsSection(analysis, source, diagnostics, findings, catalog) {
  const businessIssues = analysis.business_issues ?? [];
  const hasBusinessIssues = businessIssues.length > 0;
  const sizeTrend = hasBusinessIssues
    ? []
    : mergeSizeTrend(diagnostics, source.date_range?.date_to);
  const hotspotBenchmarks = hasBusinessIssues ? [] : hotspotGroups(diagnostics);
  const smallTrend = diagnostics.get("FIT_TOO_SMALL")?.trend_summary ?? {};
  const largeTrend = diagnostics.get("FIT_TOO_LARGE")?.trend_summary ?? {};
  return {
    diagnosticFinding: findings.diagnosticFinding,
    hasBusinessIssues,
    businessIssues,
    smallTrend,
    largeTrend,
    sizeTrend,
    hotspotBenchmarks,
    otherFindings: findings.otherFindings,
    catalog,
  };
}

/** @param {InsightReportAnalysis} analysis @param {Diagnostics} diagnostics @param {ReportFindings["informationFinding"]} informationFinding @param {InsightEvidenceCatalog} catalog */
function informationSection(analysis, diagnostics, informationFinding, catalog) {
  const informationReasonCode = findingReasonCode(informationFinding);
  const informationDiagnostic = diagnostics.get(informationReasonCode);
  const informationReason =
    informationDiagnostic?.selected_reason ??
    (analysis.reasons ?? []).find(
      (item) => String(item.value) === informationReasonCode,
    );
  const informationOpinions = informationDiagnostic?.semantic_profile?.opinions ?? [];
  const informationSamples = reasonSamples(informationDiagnostic);
  return {
    informationFinding,
    informationDiagnostic,
    informationReason,
    informationOpinions,
    informationSamples,
    catalog,
  };
}

/** @param {LegacyInsightReportContent} content @param {ReturnType<typeof informationSection>} information */
function actionsSection(content, information) {
  const actionOrder = /** @type {Record<string, number>} */ ({
    "action.mapping": 0,
    "action.diagnostic": 1,
    "action.text_quality": 2,
    "action.information": 3,
    "action.scope": 4,
  });
  const actions = [...(content.actions ?? [])].sort((left, right) => {
    const priorityDifference =
      { P0: 0, P1: 1, P2: 2 }[left.priority] - { P0: 0, P1: 1, P2: 2 }[right.priority];
    return (
      priorityDifference || (actionOrder[left.id] ?? 99) - (actionOrder[right.id] ?? 99)
    );
  });
  const [primaryAction, ...followupActions] = actions;
  return {
    primaryAction,
    followupActions,
    informationFinding: information.informationFinding,
    informationDiagnostic: information.informationDiagnostic,
    informationReason: information.informationReason,
  };
}

/** @param {InsightReport} report @param {LegacyInsightReportContent} content @param {InsightReportSource} source @param {InsightReportAnalysis} analysis */
function reportContext(report, content, source, analysis) {
  const summary = analysis.summary ?? {};
  const productMapping = source.product_mapping ?? {};
  const textQuality = source.text_quality ?? report.quality_gate?.text_quality ?? {};
  const qualityStatus = report.quality_gate?.status;
  const decisionReadiness = report.quality_gate?.decision_readiness;
  const inputTokens = number(report.usage?.input_tokens);
  const outputTokens = number(report.usage?.output_tokens);
  return {
    cover: { content, source, qualityStatus, decisionReadiness },
    summary: { content, summary, source, productMapping, textQuality },
    appendix: { inputTokens, outputTokens },
  };
}

/** @param {InsightReport} report */
export function legacyReportSections(report) {
  const content = /** @type {LegacyInsightReportContent} */ (report.content ?? {});
  const evidence = report.evidence ?? {};
  const analysis = evidence.analysis ?? {};
  const source = evidence.source ?? {};
  const catalog = evidence.catalog ?? {};
  const diagnostics = diagnosticMap(analysis);
  const findings = reportFindings(content);
  const information = informationSection(
    analysis,
    diagnostics,
    findings.informationFinding,
    catalog,
  );
  return {
    ...reportContext(report, content, source, analysis),
    structure: structureSection(analysis, findings, catalog),
    diagnostics: diagnosticsSection(analysis, source, diagnostics, findings, catalog),
    information,
    actions: actionsSection(content, information),
    boundary: { content },
  };
}
