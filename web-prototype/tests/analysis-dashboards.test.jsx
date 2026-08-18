import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { dashboardApiMock, resultApiMock } = vi.hoisted(() => ({
  dashboardApiMock: {
    dashboardPreflight: vi.fn(),
    createAnalysisDashboard: vi.fn(),
    createAnalysisDashboardVersion: vi.fn(),
    analysisDashboards: vi.fn(),
    analysisDashboard: vi.fn(),
    analysisDashboardVersions: vi.fn(),
    analysisDashboardSummary: vi.fn(),
    analysisDashboardSources: vi.fn(),
    analysisDashboardInsights: vi.fn(),
    analysisDashboardDrilldown: vi.fn(),
    analysisDashboardRecords: vi.fn(),
    createInsightReportFromResults: vi.fn(),
    createAnalysisDashboardInsightReport: vi.fn(),
    analysisDashboardInsightReports: vi.fn(),
    insightReport: vi.fn(),
    retryInsightReport: vi.fn(),
  },
  resultApiMock: {
    classificationResults: vi.fn(),
    classificationResultDownloadUrl: vi.fn(),
    configs: vi.fn(),
    modelPreference: vi.fn(),
  },
}));

vi.mock("../src/shared/api/dashboardApi", () => ({ dashboardApi: dashboardApiMock }));
vi.mock("../src/api", () => ({ api: resultApiMock }));

import { useHashRoute } from "../src/app/hashRouter";
import { AnalysisDashboardPage } from "../src/features/analysis-dashboards/AnalysisDashboardPage";
import {
  createDashboardSelection,
  readDashboardSelection,
} from "../src/features/analysis-dashboards/dashboardSelectionStorage";
import { ClassificationResultsPage } from "../src/pages/ClassificationResultsPage";

const readyResult = {
  version_id: "result-v1",
  version: 1,
  quality_status: "ready",
  publish_status: "published",
  store_site: "SEEKWAY:US",
  listing: "L001",
  product_names: ["产品A"],
  record_count: 10,
  unit_count: 4,
  published_at: "2026-08-12T08:00:00Z",
};

function DashboardHarness({ userId = "user-1" }) {
  const { route } = useHashRoute();
  return <AnalysisDashboardPage route={route} notify={vi.fn()} userId={userId} />;
}

function ResultsHarness({ userId = "user-1" }) {
  const { route } = useHashRoute();
  return route.page === "classification-results" ? (
    <ClassificationResultsPage route={route} notify={vi.fn()} userId={userId} />
  ) : null;
}

function planFor(ids, overrides = {}) {
  return {
    plan_hash: `plan-${ids.join("-")}`,
    ready: true,
    blockers: [],
    conflicts: [],
    filters: {},
    sources: ids.map((id, index) => ({
      result_version_id: id,
      version_no: index + 1,
      store_site: "SEEKWAY:US",
      listing: index ? "L002" : "L001",
      product_dataset_name: index ? null : "SEEKWAY:US 商品目录",
      product_version: index ? null : 3,
      record_count: 10,
      quality_status: "ready",
      published_at: "2026-08-12T08:00:00Z",
    })),
    summary: {
      source_count: ids.length,
      listing_count: ids.length,
      record_count: ids.length * 10,
      unit_count: ids.length * 4,
    },
    ...overrides,
  };
}

beforeEach(() => {
  sessionStorage.clear();
  window.location.hash = "#analysis-dashboards";
  Object.values(dashboardApiMock).forEach((mock) => mock.mockReset());
  Object.values(resultApiMock).forEach((mock) => mock.mockReset());
  resultApiMock.classificationResultDownloadUrl.mockReturnValue("/download");
  resultApiMock.configs.mockResolvedValue([
    {
      id: "connection-1",
      name: "OpenAI 主接入",
      active_version_id: "config-version-1",
      models: [
        {
          id: "model-1",
          model_key: "gpt-5.2",
          display_name: "GPT-5.2",
          active: true,
          validation_status: "validated",
          supported_efforts: ["low", "medium", "high"],
        },
      ],
    },
  ]);
  resultApiMock.modelPreference.mockResolvedValue(null);
  dashboardApiMock.analysisDashboards.mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
  });
  dashboardApiMock.analysisDashboard.mockResolvedValue({
    id: "dashboard-default",
    name: "默认看板",
    status: "active",
    current_version_id: "dashboard-version-default",
    revision: 1,
    version: {
      version_id: "dashboard-version-default",
      version: 1,
      dataset_version_id: "dataset-version-default",
    },
  });
  dashboardApiMock.analysisDashboardVersions.mockResolvedValue([
    {
      version_id: "dashboard-version-default",
      version: 1,
      dataset_version_id: "dataset-version-default",
    },
  ]);
  dashboardApiMock.analysisDashboardSummary.mockResolvedValue({ record_count: 0 });
  dashboardApiMock.analysisDashboardInsights.mockResolvedValue({
    summary: { record_count: 0 },
    date_range: {},
    filter_options: {},
    category_groups: [],
    total_record_count: 0,
    reasons: [],
    selected_reason: null,
    trend: [],
    products: [],
    co_reasons: [],
    evidence: { items: [], total: 0 },
  });
  dashboardApiMock.analysisDashboardDrilldown.mockResolvedValue({ items: [] });
  dashboardApiMock.analysisDashboardRecords.mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
  });
  dashboardApiMock.analysisDashboardInsightReports.mockResolvedValue([]);
});

afterEach(() => cleanup());

test("空态只保留一个选择分类结果入口", async () => {
  render(
    <AnalysisDashboardPage
      route={{ page: "analysis-dashboards", query: {} }}
      notify={vi.fn()}
      userId="user-1"
    />,
  );

  expect(await screen.findByText("还没有分析看板")).toBeVisible();
  expect(screen.getAllByRole("button", { name: "选择分类结果" })).toHaveLength(1);
});

test("分类结果选择跨分页恢复且需复核版本也可纳入", async () => {
  const user = userEvent.setup();
  const token = createDashboardSelection("user-1");
  const reviewResult = {
    ...readyResult,
    version_id: "result-review",
    listing: "L002",
    quality_status: "review_required",
  };
  resultApiMock.classificationResults.mockResolvedValue({
    items: [readyResult, reviewResult],
    total: 2,
    page: 1,
    page_size: 20,
  });
  window.location.hash = `#classification-results?selection_token=${token}`;
  const view = render(<ResultsHarness />);

  const readyCheckbox = await screen.findByRole("checkbox", {
    name: "选择 L001 结果 v1",
  });
  await user.click(readyCheckbox);
  expect(screen.getByText("已选 1 个结果版本")).toBeVisible();
  const reviewCheckbox = screen.getByRole("checkbox", {
    name: "选择 L002 结果 v1",
  });
  expect(reviewCheckbox).toBeEnabled();
  await user.click(reviewCheckbox);
  expect(screen.getByText("已选 2 个结果版本")).toBeVisible();

  view.unmount();
  window.location.hash = `#classification-results?selection_token=${token}&page=2`;
  render(<ResultsHarness />);
  expect(
    await screen.findByRole("checkbox", { name: "选择 L001 结果 v1" }),
  ).toBeChecked();
  expect(readDashboardSelection("user-1", token).selected).toHaveLength(2);
  expect(readDashboardSelection("user-2", token)).toBeNull();
});

test("分类结果可直接创建真实AI报告任务并进入报告页", async () => {
  const user = userEvent.setup();
  resultApiMock.classificationResults.mockResolvedValue({
    items: [readyResult],
    total: 1,
    page: 1,
    page_size: 20,
  });
  dashboardApiMock.dashboardPreflight.mockResolvedValue(planFor(["result-v1"]));
  dashboardApiMock.createInsightReportFromResults.mockResolvedValue({
    dashboard: {
      id: "dashboard-insight",
      version: { version_id: "dashboard-version-insight" },
    },
    report: { id: "report-insight", status: "queued" },
  });
  window.location.hash = "#classification-results";
  render(<ResultsHarness />);

  await user.click(await screen.findByRole("checkbox", { name: "选择 L001 结果 v1" }));
  await user.click(await screen.findByRole("button", { name: "生成 AI 洞察" }));
  expect(
    await screen.findByRole("heading", { name: "生成 AI 洞察报告" }),
  ).toBeVisible();
  expect(screen.getByLabelText("模型")).toHaveValue("model-1");
  expect(screen.getByRole("button", { name: "高" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  await user.click(screen.getByRole("button", { name: "开始生成" }));

  await waitFor(() =>
    expect(dashboardApiMock.createInsightReportFromResults).toHaveBeenCalledWith({
      result_version_ids: ["result-v1"],
      filters: {},
      plan_hash: "plan-result-v1",
      model_id: "model-1",
      reasoning_effort: "high",
    }),
  );
  expect(window.location.hash).toContain("dashboard=dashboard-insight");
  expect(window.location.hash).toContain("version=dashboard-version-insight");
  expect(window.location.hash).toContain("tab=report");
  expect(window.location.hash).toContain("report=report-insight");
});

test("冲突必须逐组单选后才能创建不可变看板", async () => {
  const user = userEvent.setup();
  const second = { ...readyResult, version_id: "result-v2", version: 2 };
  const token = createDashboardSelection("user-1", {
    selected: [
      {
        result_version_id: "result-v1",
        result_version_no: 1,
        store_site: "SEEKWAY:US",
        listing: "L001",
        quality_status: "ready",
        record_count: 10,
      },
      {
        result_version_id: "result-v2",
        result_version_no: 2,
        store_site: "SEEKWAY:US",
        listing: "L001",
        quality_status: "ready",
        record_count: 12,
      },
    ],
  });
  resultApiMock.classificationResults.mockResolvedValue({
    items: [readyResult, second],
    total: 2,
    page: 1,
    page_size: 20,
  });
  dashboardApiMock.dashboardPreflight.mockImplementation(({ result_version_ids }) =>
    Promise.resolve(
      result_version_ids.length === 2
        ? planFor(result_version_ids, {
            ready: false,
            conflicts: [
              {
                type: "duplicate_store_listing",
                store_site: "SEEKWAY:US",
                listing: "L001",
                result_version_ids: ["result-v1", "result-v2"],
              },
            ],
          })
        : planFor(result_version_ids),
    ),
  );
  dashboardApiMock.createAnalysisDashboard.mockResolvedValue({
    id: "dashboard-1",
    current_version_id: "dashboard-version-1",
    version: { version_id: "dashboard-version-1", version: 1 },
  });
  window.location.hash = `#analysis-dashboards?selection_token=${token}&step=check`;
  render(<DashboardHarness />);

  expect(await screen.findByText("同一 Listing 选择了多个结果版本")).toBeVisible();
  expect(screen.getByText("产品信息：SEEKWAY:US 商品目录 · v3")).toBeVisible();
  expect(screen.getByText("产品信息版本未记录")).toBeVisible();
  await user.click(screen.getByRole("radio", { name: /结果 v2/ }));
  await user.click(screen.getByRole("button", { name: /确认冲突选择/ }));
  expect(await screen.findByText("执行计划已生成")).toBeVisible();

  await user.type(screen.getByLabelText("看板名称"), "美国站退货看板");
  await user.type(screen.getByLabelText("生成原因"), "用于每周经营复盘");
  await user.click(screen.getByRole("button", { name: "确认生成分析看板" }));

  await waitFor(() =>
    expect(dashboardApiMock.createAnalysisDashboard).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "美国站退货看板",
        result_version_ids: ["result-v2"],
        plan_hash: "plan-result-v2",
        reason: "用于每周经营复盘",
      }),
    ),
  );
  expect(window.location.hash).toContain("dashboard=dashboard-1");
  expect(window.location.hash).toContain("version=dashboard-version-1");
});

test("创建409保留输入并刷新计划后要求再次确认", async () => {
  const user = userEvent.setup();
  const token = createDashboardSelection("user-1", {
    selected: [
      {
        result_version_id: "result-v1",
        result_version_no: 1,
        store_site: "SEEKWAY:US",
        listing: "L001",
        quality_status: "ready",
      },
    ],
  });
  dashboardApiMock.dashboardPreflight
    .mockResolvedValueOnce(planFor(["result-v1"]))
    .mockResolvedValue({ ...planFor(["result-v1"]), plan_hash: "plan-new" });
  const conflict = new Error("计划已过期");
  conflict.status = 409;
  dashboardApiMock.createAnalysisDashboard.mockRejectedValueOnce(conflict);
  window.location.hash = `#analysis-dashboards?selection_token=${token}&step=check`;
  render(<DashboardHarness />);

  expect(await screen.findByText("执行计划已生成")).toBeVisible();
  await user.type(screen.getByLabelText("看板名称"), "不能丢失的名称");
  await user.type(screen.getByLabelText("生成原因"), "不能丢失的原因");
  await user.click(screen.getByRole("button", { name: "确认生成分析看板" }));

  expect(await screen.findByText(/已保留你的输入/)).toBeVisible();
  expect(screen.getByLabelText("看板名称")).toHaveValue("不能丢失的名称");
  expect(screen.getByLabelText("生成原因")).toHaveValue("不能丢失的原因");
  expect(dashboardApiMock.createAnalysisDashboard).toHaveBeenCalledTimes(1);
});

test("需复核来源可创建看板并展示实际纳入范围", async () => {
  const token = createDashboardSelection("user-1", {
    selected: [
      {
        result_version_id: "result-review",
        result_version_no: 1,
        store_site: "SEEKWAY:US",
        listing: "L002",
        quality_status: "review_required",
      },
    ],
  });
  dashboardApiMock.dashboardPreflight.mockResolvedValue(
    planFor(["result-review"], {
      warnings: [
        {
          type: "quality_review_pending",
          message: "该版本仍有待复核数据；看板仅统计质量状态为 ready 的记录",
        },
      ],
      filters: { quality_status: ["ready"] },
      summary: {
        source_count: 1,
        listing_count: 1,
        record_count: 6,
        total_record_count: 10,
        pending_review_record_count: 3,
        excluded_record_count: 1,
      },
    }),
  );
  window.location.hash = `#analysis-dashboards?selection_token=${token}&step=check`;
  render(<DashboardHarness />);

  expect(await screen.findByText("当前看板将按可用范围生成")).toBeVisible();
  expect(screen.getByText(/纳入 6 \/\s*10 条记录/)).toBeVisible();
  expect(screen.getByText(/待复核 3 条；已排除 1 条/)).toBeVisible();
  expect(screen.getByRole("button", { name: "确认生成分析看板" })).toBeDisabled();
  await userEvent.type(screen.getByLabelText("看板名称"), "部分数据看板");
  await userEvent.type(screen.getByLabelText("生成原因"), "先观察已可用数据");
  expect(screen.getByRole("button", { name: "确认生成分析看板" })).toBeEnabled();
});

test("当前看板可基于选择结果生成新版本并携带revision", async () => {
  const user = userEvent.setup();
  const token = createDashboardSelection("user-1", {
    target_dashboard_id: "dashboard-1",
    expected_revision: 7,
    selected: [
      {
        result_version_id: "result-v1",
        result_version_no: 1,
        store_site: "SEEKWAY:US",
        listing: "L001",
        quality_status: "ready",
      },
    ],
  });
  dashboardApiMock.dashboardPreflight.mockResolvedValue(planFor(["result-v1"]));
  dashboardApiMock.createAnalysisDashboardVersion.mockResolvedValue({
    id: "dashboard-1",
    current_version_id: "dashboard-version-3",
    revision: 8,
    version: { version_id: "dashboard-version-3", version: 3 },
  });
  window.location.hash = `#analysis-dashboards?selection_token=${token}&step=check`;
  render(<DashboardHarness />);

  expect(await screen.findByText("基于新分类结果创建版本")).toBeVisible();
  expect(screen.queryByLabelText("看板名称")).not.toBeInTheDocument();
  await user.type(screen.getByLabelText("版本原因"), "采用复核后的分类结果");
  await user.click(screen.getByRole("button", { name: "确认生成新版本" }));

  await waitFor(() =>
    expect(dashboardApiMock.createAnalysisDashboardVersion).toHaveBeenCalledWith(
      "dashboard-1",
      expect.objectContaining({
        expected_revision: 7,
        result_version_ids: ["result-v1"],
        reason: "采用复核后的分类结果",
      }),
    ),
  );
  expect(window.location.hash).toContain("version=dashboard-version-3");
});

test("看板详情聚焦退货原因洞察并保留证据与版本入口", async () => {
  const user = userEvent.setup();
  const version = {
    version_id: "dashboard-version-2",
    dashboard_id: "dashboard-1",
    version: 2,
    dataset_version_id: "dataset-version-2",
    reason: "更新分类结果",
    created_by_name: "系统管理员",
    created_at: "2026-08-12T09:00:00Z",
  };
  dashboardApiMock.analysisDashboard.mockResolvedValue({
    id: "dashboard-1",
    name: "退货经营看板",
    description: "真实看板",
    status: "active",
    current_version_id: version.version_id,
    revision: 2,
    version,
  });
  dashboardApiMock.analysisDashboardVersions.mockResolvedValue([version]);
  const record = {
    id: "record-1",
    source_record_id: "return:1",
    order_id: "ORDER-1",
    store_site: "SEEKWAY:US",
    listing: "L001",
    product_name: null,
    product_sku: "PRODUCT-SKU-1",
    source_sku: "SOURCE-MSKU-1",
    matched_msku: "SOURCE-MSKU-1",
    category_b: "不能作为产品名称",
    amazon_reason: "TOO_SMALL",
    comment: "too small",
    problem_labels: ["FIT_TOO_SMALL"],
    classification: {
      primary_label_codes: ["FIT_TOO_SMALL"],
      model_name: "gpt-test",
    },
    evidence: [{ label_code: "FIT_TOO_SMALL", evidence: "too small" }],
  };
  dashboardApiMock.analysisDashboardInsights.mockResolvedValue({
    summary: {
      record_count: 2000,
      total_record_count: 2300,
      pending_review_record_count: 250,
    },
    date_range: { date_from: "2026-04-19", date_to: "2026-08-01" },
    filter_options: {
      listings: ["L001"],
      product_names: ["产品A"],
      product_skus: ["PRODUCT-SKU-1"],
    },
    category_groups: ["尺码与合脚", "外观"],
    total_record_count: 2000,
    reasons: [
      {
        value: "FIT_TOO_SMALL",
        label: "偏小",
        label_group: "尺码与合脚",
        record_count: 55,
        percentage: 2.8,
      },
    ],
    selected_reason: {
      value: "FIT_TOO_SMALL",
      label: "偏小",
      label_group: "尺码与合脚",
      record_count: 55,
      percentage: 2.8,
    },
    trend: [
      {
        period_start: "2026-07-27",
        period_end: "2026-08-02",
        record_count: 8,
        total_record_count: 20,
        percentage: 40,
      },
    ],
    products: [
      {
        value: "产品A",
        record_count: 32,
        reason_share: 58.2,
        product_reason_rate: 29.1,
      },
    ],
    co_reasons: [
      { value: "FIT_TOO_SHORT", label: "偏短", record_count: 12, percentage: 21.8 },
    ],
    evidence: { items: [record], total: 55 },
  });
  window.location.hash =
    "#analysis-dashboards?dashboard=dashboard-1&version=dashboard-version-2&tab=overview&problem=FIT_TOO_SMALL&listing=L001&product_name=%E4%BA%A7%E5%93%81A&product_sku=PRODUCT-SKU-1&order_id=ORDER-1";
  render(<DashboardHarness />);

  expect(await screen.findByText("退货经营看板")).toBeVisible();
  expect(screen.getByText("退货原因洞察")).toBeVisible();
  expect(screen.getByText(/已分析 2,000\/2,300 条/)).toBeVisible();
  expect(screen.getByText("具体退货原因")).toBeVisible();
  expect(screen.getByText("偏小原因占比趋势")).toBeVisible();
  await waitFor(() =>
    expect(dashboardApiMock.analysisDashboardInsights).toHaveBeenCalledWith(
      "dashboard-1",
      "dashboard-version-2",
      expect.objectContaining({
        problem: "FIT_TOO_SMALL",
        listing: "L001",
        product_name: "产品A",
        product_sku: "PRODUCT-SKU-1",
      }),
      expect.any(Object),
    ),
  );
  const recordRow = screen.getByText("too small").closest("article");
  expect(within(recordRow).getByText("未提供产品")).toBeVisible();
  expect(screen.queryByText("不能作为产品名称")).not.toBeInTheDocument();

  const evidenceButton = within(recordRow).getByRole("button", { name: /查看证据/ });
  await user.click(evidenceButton);
  const closeButton = screen.getByRole("button", { name: "关闭证据抽屉" });
  expect(closeButton).toHaveFocus();
  expect(screen.getByText("TOO_SMALL")).toBeVisible();
  await user.keyboard("{Escape}");
  expect(evidenceButton).toHaveFocus();

  await user.click(screen.getByRole("button", { name: "数据说明" }));
  await user.click(screen.getByRole("button", { name: "创建新版本" }));
  await waitFor(() => expect(window.location.hash).toContain("classification-results"));
  const token = new URLSearchParams(window.location.hash.split("?")[1]).get(
    "selection_token",
  );
  expect(readDashboardSelection("user-1", token)).toEqual(
    expect.objectContaining({
      target_dashboard_id: "dashboard-1",
      expected_revision: 2,
    }),
  );
});

test("AI洞察报告按结论证据和行动路径展开", async () => {
  const user = userEvent.setup();
  const version = {
    version_id: "dashboard-version-report",
    version: 1,
    dataset_version_id: "dataset-version-report",
  };
  dashboardApiMock.analysisDashboard.mockResolvedValue({
    id: "dashboard-report",
    name: "SR001退货分类260814",
    current_version_id: version.version_id,
    revision: 1,
    version,
  });
  dashboardApiMock.analysisDashboardVersions.mockResolvedValue([version]);
  const completedReport = {
    id: "report-1",
    kind: "report",
    attempt_no: 2,
    dashboard_id: "dashboard-report",
    dashboard_version_id: version.version_id,
    dashboard_version_no: 1,
    version_no: 1,
    status: "completed",
    model_key: "gpt-5.2",
    model_name: "GPT-5.2",
    resolved_model: "gpt-5.2-2026-08-01",
    reasoning_effort: "high",
    prompt_version: "ai-return-insight-v3",
    evidence_hash: "evidence-hash-1234567890",
    completed_at: "2026-08-15T08:30:00Z",
    usage: { input_tokens: 2100, output_tokens: 860 },
    quality_gate: {
      status: "blocked",
      consistency: {
        status: "blocked",
        issues: ["信息诊断原因 OTHER_NO_LONGER_NEEDED 缺少语义诊断数据"],
      },
      decision_readiness: {
        status: "unusable",
        label: "不可使用",
        reason: "报告内部数据不一致，请重新生成报告。",
      },
    },
    content: {
      title: "SR001 退货原因洞察报告",
      executive_summary: [
        {
          title: "核心判断",
          statement: "尺码问题是当前最需要优先验证的退货问题。",
          tone: "primary",
          evidence_ids: ["group.1", "reason.SMALL"],
        },
      ],
      findings: [
        {
          id: "finding.structure",
          kind: "structure",
          title: "尺码问题集中",
          conclusion: "尺码与合脚覆盖 59.7% 的已分析退货记录。",
          interpretation: "偏小信号主要集中在黑色商品。",
          implication: "不应统一修改全部商品尺码，应先核查具体商品。",
          evidence_ids: ["group.1", "product.1"],
        },
        {
          id: "finding.diagnostic",
          kind: "diagnostic",
          title: "偏大问题正在上升",
          conclusion: "偏大近四周均值较早期上升 6.5 个百分点。",
          interpretation: "偏小和偏大方向相反，问题并非全商品统一偏码。",
          implication: "应按商品分别核对尺码表和实物，不做全局调整。",
          evidence_ids: ["trend.LARGE", "hotspot.SMALL"],
        },
        {
          id: "finding.information",
          kind: "information",
          title: "买家原因仍需拆解",
          conclusion: "买家原因中多数没有明确到商品部位。",
          interpretation: "宽泛标签混合了顾客意图和订单操作。",
          implication: "应先改善原因采集，再决定是否转化为商品整改。",
          evidence_ids: ["reason.OTHER_NO_LONGER_NEEDED", "opinion.BUYER"],
        },
      ],
      actions: [
        {
          id: "action.diagnostic",
          priority: "P0",
          target: "SR001-801黑色 · 偏小",
          action: "核查 SR001-801 黑色尺码表与实物偏差",
          rationale: "该商品偏小信号高于整体水平。",
          success_signal: "偏小问题占比连续两个周期下降",
          evidence_ids: ["product.1"],
        },
      ],
      further_questions: ["黑色商品是否来自同一生产批次？"],
      caveats: ["报告基于退货样本，不能解释真实退货率。"],
    },
    evidence: {
      source: {
        date_range: { date_from: "2026-04-19", date_to: "2026-08-01" },
        label_coverage: 98,
        report_status: "provisional",
        product_mapping: {
          status: "needs_review",
          note: "部分商品主数据名称前缀与当前 Listing 不一致。",
        },
      },
      catalog: {
        scope: { label: "分析范围", value: "纳入 248 条，待审核 70 条" },
        "group.1": { label: "尺码与合脚", value: "148 条 · 59.7%" },
        "reason.SMALL": { label: "偏小", value: "55 条 · 22.2%" },
        "reason.OTHER_NO_LONGER_NEEDED": {
          label: "不再需要",
          value: "60 条 · 24.2%",
        },
        "product.1": { label: "SR001-801黑色", value: "110 条已分析退货" },
        "trend.LARGE": { label: "偏大趋势", value: "近四周较早期 +6.5pp" },
        "hotspot.SMALL": { label: "偏小热点", value: "商品内 29.1% · 整体 22.2%" },
        "opinion.BUYER": { label: "买家具体意图", value: "改变主意 36 条" },
      },
      analysis: {
        summary: {
          record_count: 248,
          pending_review_record_count: 70,
          excluded_record_count: 0,
        },
        label_group_breakdown: [
          { value: "尺码与合脚", record_count: 148, percentage: 59.7 },
          { value: "买家原因", record_count: 60, percentage: 24.2 },
        ],
        reasons: [
          {
            value: "FIT_TOO_SMALL",
            label: "偏小",
            record_count: 55,
            percentage: 22.2,
          },
          {
            value: "FIT_TOO_LARGE",
            label: "偏大",
            record_count: 43,
            percentage: 17.3,
          },
          {
            value: "OTHER_NO_LONGER_NEEDED",
            label: "不再需要",
            record_count: 60,
            percentage: 24.2,
          },
        ],
        diagnostics: [
          {
            reason_code: "FIT_TOO_SMALL",
            selected_reason: {
              value: "FIT_TOO_SMALL",
              label: "偏小",
              record_count: 55,
              percentage: 22.2,
            },
            trend: [
              ["2026-06-08", 25.1],
              ["2026-06-15", 24.3],
              ["2026-06-22", 23.6],
              ["2026-06-29", 22.2],
              ["2026-07-06", 21.8],
              ["2026-07-13", 20.7],
              ["2026-07-20", 19.8],
              ["2026-07-27", 19.1],
            ].map(([period_start, percentage]) => ({
              period_start,
              period_end: period_start,
              percentage,
              low_sample: false,
            })),
            hotspots: [
              {
                value: "SR001-801黑色",
                record_count: 32,
                total_record_count: 110,
                product_reason_rate: 29.1,
                overall_reason_rate: 22.2,
                lift: 1.31,
                excess_record_count: 7.6,
              },
            ],
            samples: [],
          },
          {
            reason_code: "FIT_TOO_LARGE",
            selected_reason: {
              value: "FIT_TOO_LARGE",
              label: "偏大",
              record_count: 43,
              percentage: 17.3,
            },
            trend: [
              ["2026-06-08", 13.8],
              ["2026-06-15", 14.5],
              ["2026-06-22", 15.2],
              ["2026-06-29", 16.1],
              ["2026-07-06", 17.4],
              ["2026-07-13", 18.2],
              ["2026-07-20", 19.5],
              ["2026-07-27", 20.3],
            ].map(([period_start, percentage]) => ({
              period_start,
              period_end: period_start,
              percentage,
              low_sample: false,
            })),
            hotspots: [],
            samples: [],
          },
        ],
        product_reason_matrix: [
          {
            value: "SR001-801黑色",
            total_record_count: 110,
            reliable: true,
            reason_rates: {
              SMALL: { label: "偏小", record_count: 32, percentage: 29.1, lift: 1.31 },
            },
          },
        ],
        samples: [
          {
            comment: "The shoes run small.",
            product_name: "SR001-801黑色",
          },
        ],
      },
    },
  };
  const failedReport = {
    id: "report-failed",
    kind: "generation_job",
    attempt_no: 1,
    version_no: null,
    status: "failed",
    model_key: "gpt-5.6-luna",
    model_name: "5.6 Luna",
    reasoning_effort: "high",
    error: "报告生成未完成，请稍后重试。",
  };
  dashboardApiMock.analysisDashboardInsightReports.mockResolvedValue([
    failedReport,
    completedReport,
  ]);
  window.location.hash =
    "#analysis-dashboards?dashboard=dashboard-report&version=dashboard-version-report";
  render(<DashboardHarness />);

  await user.click(await screen.findByRole("button", { name: "AI 洞察报告" }));

  expect(await screen.findByText("SR001 退货原因洞察报告")).toBeVisible();
  expect(screen.getByRole("heading", { name: "执行摘要" })).toBeVisible();
  expect(
    screen.getAllByText("尺码问题是当前最需要优先验证的退货问题。")[0],
  ).toBeVisible();
  expect(screen.getByText("尺码问题集中")).toBeVisible();
  expect(
    screen.getByText("不应统一修改全部商品尺码，应先核查具体商品。"),
  ).toBeVisible();
  expect(screen.getAllByText("SR001-801黑色")[0]).toBeVisible();
  expect(screen.getByText("偏小与偏大问题占比趋势")).toBeVisible();
  expect(screen.getByText("商品热点与整体基线")).toBeVisible();
  expect(screen.getByText("买家原因仍需拆解")).toBeVisible();
  expect(screen.getByText("不再需要占已纳入样本")).toBeVisible();
  expect(screen.getAllByText("24.2%")[0]).toBeVisible();
  expect(screen.queryByText("0.0%")).not.toBeInTheDocument();
  expect(screen.getByText(/当前历史报告未保存该原因的语义诊断/)).toBeVisible();
  expect(screen.getByText("生成完成")).toBeVisible();
  expect(screen.getByText("质量阻断")).toBeVisible();
  expect(screen.getByText("不可使用")).toBeVisible();
  expect(screen.getByText(/部分商品主数据名称前缀/)).toBeVisible();
  expect(screen.getByText("SR001-801黑色 · 偏小")).toBeVisible();
  expect(screen.getByText("核查 SR001-801 黑色尺码表与实物偏差")).toBeVisible();
  expect(screen.getByText("报告基于退货样本，不能解释真实退货率。")).toBeVisible();
  expect(window.location.hash).toContain("tab=report");
  expect(window.location.hash).toContain("report=report-1");

  await user.click(screen.getByText("生成记录"));
  await user.click(screen.getByRole("button", { name: "查看生成尝试 1" }));
  expect(
    await screen.findByRole("heading", { name: "这是一次历史生成失败" }),
  ).toBeVisible();
  expect(screen.queryByRole("button", { name: "重试" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "查看最新报告" }));
  expect(await screen.findByText("SR001 退货原因洞察报告")).toBeVisible();

  const queuedReport = {
    ...completedReport,
    id: "report-2",
    kind: "generation_job",
    attempt_no: 3,
    version_no: null,
    status: "queued",
    content: null,
    evidence: null,
  };
  dashboardApiMock.createAnalysisDashboardInsightReport.mockResolvedValue(queuedReport);
  dashboardApiMock.analysisDashboardInsightReports.mockResolvedValue([
    queuedReport,
    completedReport,
  ]);
  await user.click(screen.getByRole("button", { name: "重新生成" }));
  expect(
    await screen.findByRole("heading", { name: "生成 AI 洞察报告" }),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "开始生成" }));
  await waitFor(() =>
    expect(dashboardApiMock.createAnalysisDashboardInsightReport).toHaveBeenCalledWith(
      "dashboard-report",
      "dashboard-version-report",
      { model_id: "model-1", reasoning_effort: "high" },
    ),
  );
  expect(await screen.findByText("AI 正在生成洞察报告")).toBeVisible();
  expect(window.location.hash).toContain("report=report-2");
});

test("数据来源与版本历史使用真实看板版本字段", async () => {
  const user = userEvent.setup();
  const versions = [
    {
      version_id: "dashboard-version-2",
      version: 2,
      dataset_version_id: "dataset-version-2",
      reason: "替换 L001 分类结果",
      created_by_name: "运营甲",
      created_at: "2026-08-12T09:00:00Z",
    },
    {
      version_id: "dashboard-version-1",
      version: 1,
      dataset_version_id: "dataset-version-1",
      reason: "首次生成",
      created_by_name: "运营乙",
      created_at: "2026-08-11T09:00:00Z",
    },
  ];
  dashboardApiMock.analysisDashboard.mockResolvedValue({
    id: "dashboard-1",
    name: "来源可追溯看板",
    status: "active",
    current_version_id: "dashboard-version-2",
    revision: 2,
    version: versions[0],
  });
  dashboardApiMock.analysisDashboardVersions.mockResolvedValue(versions);
  dashboardApiMock.analysisDashboardSources.mockResolvedValue([
    {
      result_version_id: "result-version-8",
      version_no: 8,
      store_site: "SEEKWAY:US",
      listing: "L001",
      product_dataset_name: "SEEKWAY:US 商品目录",
      product_version: 3,
      record_count: 120,
      quality_status: "ready",
    },
    {
      result_version_id: "result-version-7",
      version_no: 7,
      store_site: "SEEKWAY:US",
      listing: "L002",
      record_count: 20,
      quality_status: "ready",
    },
  ]);
  window.location.hash =
    "#analysis-dashboards?dashboard=dashboard-1&version=dashboard-version-2&tab=source";
  render(<DashboardHarness />);

  expect(await screen.findByText("数据来源与血缘")).toBeVisible();
  expect(
    screen.getByText(/看板 v2 → 看板数据集 v2 → Listing 分类结果版本/),
  ).toBeVisible();
  expect(screen.getByText("dataset-version-2")).toBeVisible();
  expect(screen.getByText("v8")).toBeVisible();
  expect(screen.getByText("SEEKWAY:US 商品目录 · v3")).toBeVisible();
  expect(screen.getByText("未提供产品信息版本")).toBeVisible();

  await user.click(screen.getByRole("button", { name: "版本历史" }));
  expect(await screen.findByText("看板版本历史")).toBeVisible();
  expect(screen.getByText("看板数据集 v2")).toBeVisible();
  expect(screen.getByText("替换 L001 分类结果")).toBeVisible();
  expect(screen.getByText("首次生成")).toBeVisible();
  expect(window.location.hash).toContain("tab=history");
});

test("旧列表响应不能覆盖新筛选结果", async () => {
  let resolveOld;
  const oldResponse = new Promise((resolve) => {
    resolveOld = resolve;
  });
  dashboardApiMock.analysisDashboards.mockImplementation((filters) => {
    if (filters.q === "旧") return oldResponse;
    return Promise.resolve({
      items: [
        {
          id: "dashboard-new",
          name: "新筛选看板",
          status: "active",
          current_version: 2,
          summary: { listing_count: 1, record_count: 10 },
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
  });
  const oldRoute = {
    page: "analysis-dashboards",
    query: { q: "旧" },
  };
  const view = render(
    <AnalysisDashboardPage route={oldRoute} notify={vi.fn()} userId="user-1" />,
  );
  view.rerender(
    <AnalysisDashboardPage
      route={{ page: "analysis-dashboards", query: { q: "新" } }}
      notify={vi.fn()}
      userId="user-1"
    />,
  );
  expect(await screen.findByText("新筛选看板")).toBeVisible();
  await act(async () => {
    resolveOld({
      items: [
        {
          id: "dashboard-old",
          name: "旧响应看板",
          status: "active",
          current_version: 1,
          summary: { listing_count: 1, record_count: 1 },
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
  });
  expect(screen.queryByText("旧响应看板")).not.toBeInTheDocument();
  expect(screen.getByText("新筛选看板")).toBeVisible();
});
