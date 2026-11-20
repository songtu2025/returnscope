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

test("V8 以连续主题章节呈现事实、假设、行动、证据和末尾边界", async () => {
  const theme = {
    id: "theme.1",
    name: "质量与耐用",
    title: "耐用性反馈集中在早期使用",
    priority: "P0",
    facts: ["8 / 15 条反馈涉及耐用性"],
    evidence_ids: ["scope"],
    diagnosis: "提前核对失效条件。",
    hypothesis: "待验证使用环境差异。",
    impact: "可能影响使用体验。",
    action: "复核早期反馈。",
    metric: "跟踪同口径的样本占比。",
  };
  const themedReport = {
    ...report,
    id: "report-v8",
    version_no: 2,
    prompt_version: "ai-semantic-insight-v8",
    content: {
      report_type: "theme_insight",
      title: "关注耐用性与使用体验",
      executive_summary: [
        {
          title: "质量与耐用",
          statement: "优先查看失效反馈。",
          evidence_ids: ["scope"],
        },
      ],
      themes: [theme],
      boundaries: ["占比描述当前反馈样本。"],
    },
  };
  const props = renderReport({ report: themedReport, reports: [themedReport, report] });
  const user = userEvent.setup();
  render(<AiInsightReport {...props} />);
  expect(screen.getByRole("heading", { name: "当前产品判断" })).toBeVisible();
  const chapter = screen.getByRole("region", { name: theme.title });
  expect(within(chapter).getByText(theme.facts[0])).toBeVisible();
  expect(within(chapter).getByText(theme.hypothesis)).toBeVisible();
  expect(within(chapter).getByText(theme.metric)).toBeVisible();
  expect(within(chapter).getByText("统计范围")).not.toBeVisible();
  await user.click(within(chapter).getByText("查看证据（1 项）"));
  expect(within(chapter).getByText("统计范围")).toBeVisible();
  expect(screen.getByRole("region", { name: "数据边界" })).toBeVisible();
  await user.selectOptions(
    screen.getByRole("combobox", { name: "报告版本" }),
    report.id,
  );
  expect(props.onSelect).toHaveBeenCalledWith(report.id);
});

test("V9 按简报版式展示结论、优先级和默认折叠的口径证据", async () => {
  const fact = "其中 8 条提及短期失效。";
  const concise = {
    ...report,
    id: "report-v9",
    prompt_version: "ai-semantic-insight-v9",
    content: {
      report_type: "concise_insight",
      title: "耐用性应排在改进首位",
      judgment: "优先验证短期失效，同时保留改款的舒适体验。",
      insights: [
        {
          id: "quality",
          title: "短期失效值得先解决",
          fact,
          meaning: "复验连接部位。",
          evidence_ids: ["scope"],
        },
      ],
      actions: [
        {
          id: "quality",
          priority: "P0",
          title: "复现短期失效",
          action: "用同款样品对照测试。",
          evidence_ids: ["scope"],
        },
      ],
      closing: "先稳定耐用表现，再扩大产品卖点。",
      boundaries: ["占比描述当前反馈样本。"],
    },
  };
  const user = userEvent.setup();
  render(<AiInsightReport {...renderReport({ report: concise })} />);
  expect(screen.getByRole("heading", { name: concise.content.title })).toBeVisible();
  expect(screen.getByRole("heading", { name: "核心洞察" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "产品行动优先级" })).toBeVisible();
  expect(screen.getByText("P0")).toBeVisible();
  expect(screen.getAllByText(fact)).toHaveLength(1);
  expect(screen.queryByRole("heading", { name: "观察事实" })).not.toBeInTheDocument();
  expect(screen.getByText(concise.content.boundaries[0])).not.toBeVisible();
  await user.click(screen.getByRole("link", { name: "短期失效值得先解决" }));
  expect(screen.getByText(concise.content.boundaries[0])).toBeVisible();
  expect(screen.getByText("统计范围")).toBeVisible();
});

test("V10 以键盘展开本章证据并定位冻结关联的分类反馈组", async () => {
  const metric = {
    label: "短期表达命中",
    numerator: 85,
    denominator: 200,
    percent: 42.5,
    unit: "条",
    scope: "质量负向反馈",
  };
  const chapter = {
    id: "durability",
    name: "耐用性与短期失效",
    title: "优先复现短期耐用性问题",
    metrics: [metric],
    breakdown: [],
    explanation: "按使用时间区分复现条件。",
    boundary: "无法估算总体发生率。",
    action: "对照同款样品。",
    definition: "文本规则命中按反馈去重。",
    records: [
      {
        record_id: "classification-record",
        source_record_id: "source-record",
        result_version_id: "classification-version",
        source_row: 97,
        excerpt: "Example report excerpt",
        reason: "命中短期表达",
      },
    ],
  };
  const verifiedReport = {
    ...report,
    id: "report-10",
    prompt_version: "ai-semantic-insight-v10",
    content: {
      report_type: "verifiable_insight",
      title: "先验证耐用性",
      chapters: [chapter],
      summary: [{ label: "优先验证", text: "复现短期失效。" }],
      actions: [],
      boundaries: ["当前范围仅代表反馈样本。"],
    },
  };
  const user = userEvent.setup();
  render(
    <AiInsightReport
      {...renderReport({ report: verifiedReport, reports: [verifiedReport, report] })}
    />,
  );
  const region = screen.getByRole("region", { name: chapter.title });
  const button = within(region).getByRole("button", { name: /核查证据/ });
  expect(within(region).getByText("85 / 200 条")).toBeVisible();
  expect(button).toHaveAttribute("aria-expanded", "false");
  button.focus();
  await user.keyboard("{Enter}");
  expect(button).toHaveAttribute("aria-expanded", "true");
  expect(within(region).getByText(chapter.definition)).toBeVisible();
  expect(within(region).getByRole("link", { name: /查看分类反馈组/ })).toHaveAttribute(
    "href",
    expect.stringContaining("feedback_source_record_id=source-record"),
  );
  await user.keyboard(" ");
  expect(button).toHaveAttribute("aria-expanded", "false");
  expect(button).toHaveFocus();
});
