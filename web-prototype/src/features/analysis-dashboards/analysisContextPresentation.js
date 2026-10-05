const DEFAULT_ANALYSIS_CONTEXT = "user_feedback";

const ANALYSIS_CONTEXT_TERMS = {
  user_feedback: {
    pageTitle: "用户反馈语义洞察",
    reportTitle: "AI 用户反馈语义洞察报告",
    filterAria: "用户反馈语义洞察筛选",
    reasonChooserAria: "选择主题与反馈原因",
    reasonCategoryAria: "反馈原因类别",
    reasonHeading: "具体反馈原因",
    includedLabel: "有效反馈",
    recordUnit: "反馈",
    includedRecordLabel: "可用反馈记录",
    shareLabel: "占有效反馈",
    weeklyVolumeLabel: "周反馈量",
    sourceSkuLabel: "来源 SKU（MSKU）",
    originalTextLabel: "反馈原文",
    sourceReasonLabel: "来源原因",
    missingText: "未提供反馈原文",
    sampleShareLabel: "反馈样本内占比",
    rateBoundary: "不等于总体发生率",
    sampleStructure: "反馈样本结构",
    problemStructure: "用户反馈问题结构",
    selectReasonPrompt: "请选择一个反馈原因开始诊断",
    originalFeedback: "原始用户反馈",
  },
  returns: {
    pageTitle: "退货原因洞察",
    reportTitle: "AI 退货洞察报告",
    filterAria: "退货原因洞察筛选",
    reasonChooserAria: "选择主题与退货原因",
    reasonCategoryAria: "退货原因类别",
    reasonHeading: "具体退货原因",
    includedLabel: "有效退货",
    recordUnit: "退货记录",
    includedRecordLabel: "可用退货记录",
    shareLabel: "占有效退货",
    weeklyVolumeLabel: "周退货量",
    sourceSkuLabel: "退货 SKU（MSKU）",
    originalTextLabel: "退货原文",
    sourceReasonLabel: "Amazon 原因",
    missingText: "未提供退货评论",
    sampleShareLabel: "退货样本内占比",
    rateBoundary: "不等于退货率",
    sampleStructure: "退货样本结构",
    problemStructure: "退货问题结构",
    selectReasonPrompt: "请选择一个退货原因开始诊断",
    originalFeedback: "原始退货评论",
  },
};

/** @param {unknown} value */
export function analysisContextTerms(value) {
  const context = value === "returns" ? "returns" : DEFAULT_ANALYSIS_CONTEXT;
  return { ...ANALYSIS_CONTEXT_TERMS[context] };
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
