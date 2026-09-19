const DEFAULT_ANALYSIS_CONTEXT = "user_feedback";

/** @param {unknown} value */
function isReturnsContext(value) {
  return value === "returns";
}

/** @param {unknown} value */
export function analysisContextTerms(value) {
  const returns = isReturnsContext(value);
  return {
    pageTitle: returns ? "退货原因洞察" : "用户反馈语义洞察",
    reportTitle: returns ? "AI 退货洞察报告" : "AI 用户反馈语义洞察报告",
    filterAria: returns ? "退货原因洞察筛选" : "用户反馈语义洞察筛选",
    reasonChooserAria: returns ? "选择主题与退货原因" : "选择主题与反馈原因",
    reasonCategoryAria: returns ? "退货原因类别" : "反馈原因类别",
    reasonHeading: returns ? "具体退货原因" : "具体反馈原因",
    includedLabel: returns ? "有效退货" : "有效反馈",
    recordUnit: returns ? "退货记录" : "反馈",
    includedRecordLabel: returns ? "可用退货记录" : "可用反馈记录",
    shareLabel: returns ? "占有效退货" : "占有效反馈",
    weeklyVolumeLabel: returns ? "周退货量" : "周反馈量",
    sourceSkuLabel: returns ? "退货 SKU（MSKU）" : "来源 SKU（MSKU）",
    originalTextLabel: returns ? "退货原文" : "反馈原文",
    sourceReasonLabel: returns ? "Amazon 原因" : "来源原因",
    missingText: returns ? "未提供退货评论" : "未提供反馈原文",
    sampleShareLabel: returns ? "退货样本内占比" : "反馈样本内占比",
    rateBoundary: returns ? "不等于退货率" : "不等于总体发生率",
    sampleStructure: returns ? "退货样本结构" : "反馈样本结构",
    problemStructure: returns ? "退货问题结构" : "用户反馈问题结构",
    selectReasonPrompt: returns
      ? "请选择一个退货原因开始诊断"
      : "请选择一个反馈原因开始诊断",
    originalFeedback: returns ? "原始退货评论" : "原始用户反馈",
  };
}

/**
 * @param {import("./analysisDashboardContracts").DashboardContentData | null} data
 * @param {import("./analysisDashboardContracts").InsightReport | null} report
 */
export function dashboardAnalysisContext(data, report) {
  const reportContext = report?.evidence?.source?.analysis_context;
  if (reportContext) return reportContext;
  if (data && !Array.isArray(data) && "analysis_context" in data) {
    return data.analysis_context || DEFAULT_ANALYSIS_CONTEXT;
  }
  const sources = Array.isArray(data) ? data : [];
  if (
    sources.length &&
    sources.every((source) => source.analysis_context === "returns")
  ) {
    return "returns";
  }
  return DEFAULT_ANALYSIS_CONTEXT;
}
