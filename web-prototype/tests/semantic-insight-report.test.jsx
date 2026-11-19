import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { AiInsightReport } from "../src/features/analysis-dashboards/AiInsightReport";
import { selectedDashboardIssue } from "../src/features/analysis-dashboards/dashboardReportPolicy";

afterEach(cleanup);

const baseIssue = {
  rank: 1,
  scope: { category: "商品" },
  metrics: {
    matched_return_samples: 2,
    scoped_return_samples: 10,
    return_sample_share: 20,
  },
  evidence_ids: ["scope"],
  known: ["命中样本 2 条"],
  evidence_explanation: "用于核查反馈信号",
  readiness: { status: "diagnostic_only", label: "仅供诊断" },
  recommendation: { validation_question: "同口径样本中是否重复出现？" },
};
const risk = { ...baseIssue, id: "risk", kind: "risk", title: "操作有阻碍" };
const opportunity = {
  ...baseIssue,
  id: "opportunity",
  kind: "opportunity",
  title: "操作便捷",
};
const report = {
  id: "report-7",
  status: "completed",
  prompt_version: "ai-semantic-insight-v7",
  version_no: 3,
  dashboard_version_no: 8,
  completed_at: "2026-11-19T00:00:00+00:00",
  content: {
    report_type: "semantic_insight",
    title: "反馈信号与验证方向",
    overview: {
      total: 10,
      labeled: 8,
      label_coverage: 80,
      positive: 3,
      negative: 2,
      mixed: 1,
      unclear: 4,
    },
    executive_summary: [
      { title: "分布摘要", statement: "已纳入样本", evidence_ids: ["scope"] },
    ],
    issues: [risk, opportunity],
    caveats: ["占比仅描述当前样本"],
  },
  evidence: {
    source: {
      total_record_count: 12,
      included_record_count: 10,
      label_coverage: 80,
      pending_review_record_count: 2,
      product_mapping: { status: "needs_review", note: "存在未匹配记录" },
      text_quality: { status: "needs_review", note: "存在文本异常" },
    },
    catalog: { scope: { label: "统计范围", value: "反馈样本" } },
  },
  quality_gate: { status: "warning" },
};

function renderReport(overrides = {}) {
  return {
    onSelectIssue: vi.fn(),
    onDecision: vi.fn(),
    onSelect: vi.fn(),
    onCancel: vi.fn(),
    onGenerate: vi.fn(),
    onRetry: vi.fn(),
    report,
    reports: [report],
    latestReport: report,
    decisionState: { loading: false },
    version: null,
    selectedIssueId: "opportunity",
    analysisContext: "user_feedback",
    ...overrides,
  };
}

test("V7 以连续阅读报告展示全部洞察、证据和数据边界", async () => {
  const props = renderReport();
  const user = userEvent.setup();
  render(<AiInsightReport {...props} />);
  expect(screen.getByText(/数据版本 V8/)).toBeVisible();
  expect(screen.getByText(/标签覆盖率为/)).toBeVisible();
  expect(screen.getByText("存在未匹配记录")).toBeVisible();
  expect(screen.getByText("存在文本异常")).toBeVisible();
  expect(
    screen.queryByRole("navigation", { name: "洞察清单" }),
  ).not.toBeInTheDocument();
  const riskSection = screen.getByRole("region", { name: "操作有阻碍" });
  const opportunitySection = screen.getByRole("region", { name: "操作便捷" });
  expect(riskSection).toBeVisible();
  expect(opportunitySection).toBeVisible();
  expect(within(opportunitySection).getByText("用于核查反馈信号")).toBeVisible();
  expect(within(opportunitySection).getByText(/命中 2 \/ 10 条反馈/)).toBeVisible();
  await user.click(within(opportunitySection).getByText("查看 1 项证据"));
  expect(
    within(opportunitySection).getByRole("list", { name: "证据明细" }),
  ).toBeVisible();
  expect(
    within(opportunitySection).queryByRole("button", { name: "建议验证" }),
  ).not.toBeInTheDocument();
  expect(selectedDashboardIssue(report, "opportunity")).toBe("opportunity");
  expect(selectedDashboardIssue(report, "unknown")).toBe("risk");
  expect(
    selectedDashboardIssue(
      { ...report, prompt_version: "ai-return-insight-v6" },
      "opportunity",
    ),
  ).toBe("opportunity");
});

test("V7 使用已有运行视图，并保留取消与历史完成报告入口", async () => {
  const props = renderReport({
    report: { id: "job", status: "running", prompt_version: report.prompt_version },
  });
  const user = userEvent.setup();
  render(<AiInsightReport {...props} />);
  expect(screen.getByText("AI 正在生成洞察报告")).toBeVisible();
  await user.click(screen.getByRole("button", { name: /取消/ }));
  expect(props.onCancel).toHaveBeenCalledOnce();
  await user.click(screen.getByRole("button", { name: "查看已发布报告" }));
  expect(props.onSelect).toHaveBeenCalledWith(report.id);
  expect(
    screen.queryByRole("navigation", { name: "洞察清单" }),
  ).not.toBeInTheDocument();
});
