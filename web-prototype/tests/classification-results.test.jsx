import { afterEach, beforeEach, expect, test, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SWRConfig } from "swr";

const { apiMock, dashboardApiMock } = vi.hoisted(() => ({
  apiMock: {
    classificationResults: vi.fn(),
    classificationResult: vi.fn(),
    classificationResultSummary: vi.fn(),
    classificationResultRecordGroups: vi.fn(),
    classificationResultDrilldown: vi.fn(),
    classificationResultDownloadUrl: vi.fn(),
    classificationResultVersions: vi.fn(),
    reviewBatches: vi.fn(),
    createReviewBatch: vi.fn(),
    configs: vi.fn(),
    resultTaxonomy: vi.fn(),
    correctClassificationResult: vi.fn(),
  },
  dashboardApiMock: {
    dashboardPreflight: vi.fn(),
    createInsightReportFromResults: vi.fn(),
  },
}));

vi.mock("../src/api", () => ({ api: apiMock }));
vi.mock("../src/shared/api/dashboardApi", () => ({
  dashboardApi: dashboardApiMock,
}));

import { ClassificationResultsPage } from "../src/pages/ClassificationResultsPage";
import { AnalysisDashboardPage } from "../src/features/analysis-dashboards/AnalysisDashboardPage";
import { useHashRoute } from "../src/app/hashRouter";
import { readDashboardSelection } from "../src/features/analysis-dashboards/dashboardSelectionStorage";
import { ResultVersionReviewPanel } from "../src/features/review-batches/ResultVersionReviewPanel";
import { ResultVersionHistory } from "../src/features/review-batches/ResultVersionHistory";
import { renderWithServerState as render } from "./renderWithServerState";

const resultVersion = {
  version_id: "classification-version-1",
  result_id: "classification-result-1",
  version: 1,
  quality_status: "ready",
  publish_status: "published",
  store_site: "SEEKWAY:US",
  listing: "SR001",
  product_names: ["产品表权威名称", "产品表第二名称"],
  record_count: 3,
  unit_count: 1,
  analysis_context: "returns",
  agent_family: "鞋履智能体",
  product_version: 4,
  published_at: "2026-08-12T08:00:00Z",
};

function ResultCreationHarness({ notify = vi.fn() }) {
  const { route } = useHashRoute();
  if (route.page === "analysis-dashboards") {
    return route.query.selection_token ? (
      <AnalysisDashboardPage route={route} notify={notify} userId="user-1" />
    ) : null;
  }
  return <ClassificationResultsPage route={route} notify={notify} userId="user-1" />;
}

const record = {
  id: "record-1",
  result_version_id: "classification-version-1",
  source_record_id: "returns-v3:2",
  source_row: 2,
  return_date: "2026-08-01",
  order_id: "ORDER-001",
  store_site: "SEEKWAY:US",
  listing: "SR001",
  product_name: "产品表权威名称",
  source_sku: "SOURCE-MSKU-1",
  matched_msku: "SOURCE-MSKU-1",
  product_sku: "PRODUCT-SKU-1",
  category_a: "绝不可作为产品名称",
  category_b: "休闲运动水鞋",
  reason: "TOO_SMALL",
  comment: "Too small for me",
  product_match_status: "matched",
  quality_status: "ready",
  processing_status: "AUTO_APPROVED",
  classification_key: "classification-key-1",
  problem_labels: ["FIT_TOO_SMALL"],
  comment_summary_status: "NO_CONFIRMED",
  comment_conclusions: [
    {
      topic_code: "FIT_TOO_SMALL",
      topic_name: "尺码偏小",
      status: "NO_CONFIRMED",
      label_codes: ["FIT_TOO_SMALL"],
    },
  ],
  classification: {
    primary_label_codes: ["FIT_TOO_SMALL"],
    problem_label_codes: ["FIT_TOO_SMALL"],
    review_reasons: [],
    model_name: "model-primary",
    prompt_version: "prompt-v1",
    taxonomy_version: "taxonomy-v3",
    semantic_units: [
      {
        label_code: "FIT_TOO_SMALL",
        evidence: "Too small",
        part: "WHOLE_SHOE",
        opinion: "尺码偏小",
      },
    ],
    unknown_semantics: [],
  },
};

const groupOf = (value) => ({
  record: value,
  member_count: 1,
  members: [
    {
      source_record_id: value.source_record_id,
      source_row: value.source_row,
      return_date: value.return_date,
      reason: value.reason,
      comment: value.comment,
    },
  ],
});

beforeEach(() => {
  sessionStorage.clear();
  window.location.hash = "classification-results";
  Object.values(apiMock).forEach((mock) => mock.mockReset());
  Object.values(dashboardApiMock).forEach((mock) => mock.mockReset());
  apiMock.classificationResultDownloadUrl.mockImplementation(
    (id) => `/classification-results/${id}/download`,
  );
  apiMock.classificationResults.mockResolvedValue({
    items: [resultVersion],
    total: 1,
    page: 1,
    page_size: 20,
  });
  apiMock.classificationResult.mockResolvedValue(resultVersion);
  apiMock.classificationResultVersions.mockResolvedValue([resultVersion]);
  apiMock.reviewBatches.mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 100,
  });
  apiMock.configs.mockResolvedValue([
    {
      id: "connection-1",
      name: "OpenAI 主接入",
      active_version: { primary_model: "gpt-5.6" },
      models: [
        {
          id: "model-1",
          connection_id: "connection-1",
          model_key: "gpt-5.6",
          display_name: "GPT-5.6",
          supported_efforts: ["low", "medium", "high"],
          active: true,
          validation_status: "validated",
        },
      ],
    },
  ]);
  dashboardApiMock.dashboardPreflight.mockResolvedValue({
    plan_hash: "plan-ai-insight",
    ready: true,
    blockers: [],
    conflicts: [],
    summary: {
      record_count: 3,
      total_record_count: 5,
      pending_review_record_count: 1,
      excluded_record_count: 1,
    },
  });
  dashboardApiMock.createInsightReportFromResults.mockResolvedValue({
    dashboard: {
      id: "dashboard-ai-insight",
      version: { version_id: "dashboard-version-ai-insight" },
    },
    report: { id: "report-ai-insight", status: "queued" },
  });
  apiMock.classificationResultSummary.mockResolvedValue({
    version_id: resultVersion.version_id,
    quality: [{ quality_status: "ready", record_count: 3, unit_count: 1 }],
    processing_statuses: [],
    top_problems: [],
  });
  apiMock.classificationResultRecordGroups.mockResolvedValue({
    items: [groupOf(record)],
    total: 1,
    source_total: 1,
    page: 1,
    page_size: 20,
  });
  apiMock.classificationResultDrilldown.mockImplementation((_versionId, groupBy) => {
    const values = {
      problem: [
        {
          value: "FIT_TOO_SMALL",
          label_name: "偏小",
          record_count: 1,
          unit_count: 1,
        },
      ],
      product_name: [{ value: "产品表权威名称", record_count: 1, unit_count: 1 }],
      product_sku: [{ value: "PRODUCT-SKU-1", record_count: 1, unit_count: 1 }],
    };
    return Promise.resolve({
      group_by: groupBy,
      items: values[groupBy],
      total: 1,
      page: 1,
      page_size: 100,
    });
  });
});

test("分类结果使用统一列表，进入详情携带记录情况筛选", async () => {
  render(
    <ClassificationResultsPage
      route={{ query: { quality_status: "review_required" } }}
      notify={vi.fn()}
      userId="user-1"
    />,
  );
  expect(screen.queryByRole("button", { name: "结果版本" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "待复核" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "复核记录" })).not.toBeInTheDocument();
  await userEvent.click(await screen.findByRole("button", { name: "SR001" }));
  expect(window.location.hash).toContain("record_quality_status=review_required");
  expect(window.location.hash).not.toContain("view=reviews");
});

test("打开证据后晚到的版本查询不会切换页面或打断人工编辑", async () => {
  let resolveVersions;
  apiMock.resultTaxonomy.mockResolvedValue({ labels: [], parts: [] });
  apiMock.classificationResultVersions.mockImplementation(
    () =>
      new Promise((resolve) => {
        resolveVersions = resolve;
      }),
  );
  window.location.hash = "classification-results?version=classification-version-1";
  render(<ClassificationResultsPage notify={vi.fn()} />);
  await userEvent.click(await screen.findByRole("button", { name: "查看证据" }));
  const drawer = screen.getByRole("dialog", { name: "分类结果与证据" });
  await userEvent.click(within(drawer).getByRole("button", { name: "人工修正" }));
  const opinion = await within(drawer).findByRole("textbox", {
    name: "观点 1 用户观点",
  });
  await userEvent.clear(opinion);
  await userEvent.type(opinion, "保留当前草稿");
  await act(async () =>
    resolveVersions([
      { ...resultVersion, version: 2, version_id: "classification-version-2" },
    ]),
  );
  expect(screen.getByRole("dialog", { name: "分类结果与证据" })).toBeVisible();
  expect(window.location.hash).toContain("classification-version-1");
  expect(window.location.hash).not.toContain("classification-version-2");
  expect(opinion).toHaveValue("保留当前草稿");
});

test("分类结果更新失败保留内容和输入，重复失败后仍可恢复", async () => {
  window.location.hash = "classification-results?version=classification-version-1";
  render(<ClassificationResultsPage notify={vi.fn()} />);
  expect(await screen.findByRole("heading", { name: "SR001 分类结果" })).toBeVisible();
  const orderInput = screen.getByRole("textbox", { name: "搜索 order-id" });
  fireEvent.change(orderInput, { target: { value: "未提交的订单筛选" } });
  apiMock.classificationResultVersions.mockRejectedValueOnce(new Error("合成更新中断"));
  fireEvent(window, new Event("focus"));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("分类结果更新失败，当前显示上一次数据");
  expect(screen.getByRole("heading", { name: "SR001 分类结果" })).toBeVisible();
  apiMock.classificationResult.mockRejectedValueOnce(new Error("合成详情更新失败"));
  await userEvent.click(within(alert).getByRole("button", { name: "重试" }));
  expect(await screen.findByText("合成详情更新失败")).toBeVisible();
  expect(screen.getByRole("heading", { name: "SR001 分类结果" })).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "重试" }));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  expect(orderInput).toHaveValue("未提交的订单筛选");
});

test("人工编辑期间详情更新失败不关闭抽屉或清空草稿", async () => {
  apiMock.resultTaxonomy.mockResolvedValue({ labels: [], parts: [] });
  window.location.hash = "classification-results?version=classification-version-1";
  render(
    <SWRConfig value={{ focusThrottleInterval: 0 }}>
      <ClassificationResultsPage notify={vi.fn()} />
    </SWRConfig>,
  );
  await userEvent.click(await screen.findByRole("button", { name: "查看证据" }));
  const drawer = screen.getByRole("dialog", { name: "分类结果与证据" });
  await userEvent.click(within(drawer).getByRole("button", { name: "人工修正" }));
  const opinion = await within(drawer).findByRole("textbox", {
    name: "观点 1 用户观点",
  });
  await userEvent.clear(opinion);
  await userEvent.type(opinion, "更新中断时保留草稿");
  apiMock.classificationResult.mockRejectedValueOnce(new Error("合成编辑期间更新失败"));
  fireEvent(window, new Event("focus"));
  expect(await screen.findByText("合成编辑期间更新失败")).toBeInTheDocument();
  expect(screen.getByRole("dialog", { name: "分类结果与证据" })).toBeVisible();
  expect(opinion).toHaveValue("更新中断时保留草稿");
});

test("分类结果详情加载时在原页面保留返回入口与稳定占位", async () => {
  let resolveSummary;
  apiMock.classificationResultSummary.mockReturnValue(
    new Promise((resolve) => {
      resolveSummary = resolve;
    }),
  );
  window.location.hash =
    "classification-results?result_version_id=classification-version-1";

  render(<ClassificationResultsPage notify={vi.fn()} />);

  expect(await screen.findByText("正在读取分类结果详情…")).toBeVisible();
  expect(screen.getByRole("button", { name: "返回分类结果池" })).toBeVisible();
  expect(
    screen.getByText("正在读取分类结果详情…").closest(".standard-page"),
  ).toBeInTheDocument();

  await act(async () =>
    resolveSummary({
      version_id: resultVersion.version_id,
      quality: [],
      processing_statuses: [],
      top_problems: [],
    }),
  );
  expect(await screen.findByRole("button", { name: "返回分类结果池" })).toBeVisible();
  expect(screen.queryByText("正在读取分类结果详情…")).not.toBeInTheDocument();
});

test("分类结果摘要保留统计卡片且不显示记录对账说明", async () => {
  apiMock.classificationResult.mockResolvedValue({
    ...resultVersion,
    record_count: 50,
    unit_count: 45,
  });
  apiMock.classificationResultSummary.mockResolvedValue({
    version_id: resultVersion.version_id,
    quality: [
      { quality_status: "ready", record_count: 41, unit_count: 36 },
      { quality_status: "review_required", record_count: 6, unit_count: 6 },
      { quality_status: "excluded", record_count: 1, unit_count: 1 },
      { quality_status: "unusable", record_count: 2, unit_count: 2 },
    ],
    processing_statuses: [
      { processing_status: "MODEL_ERROR", record_count: 2, unit_count: 2 },
    ],
    top_problems: [],
  });
  window.location.hash =
    "classification-results?result_version_id=classification-version-1";

  render(<ClassificationResultsPage notify={vi.fn()} />);

  expect(await screen.findByText("已忽略记录")).toBeVisible();
  expect(screen.getByText("不可用记录")).toBeVisible();
  expect(screen.getByText("其中模型异常 2 条")).toBeVisible();
  expect(screen.queryByText(/记录对账：/)).not.toBeInTheDocument();
  const metrics = document.querySelector(".result-summary-grid");
  expect(Array.from(metrics.querySelectorAll("b"), (el) => el.textContent)).toEqual([
    "50",
    "45",
    "41",
    "6",
    "1",
    "2",
  ]);
});

test("用户反馈结果不再把标题展示为退货原因", async () => {
  const user = userEvent.setup();
  apiMock.classificationResult.mockResolvedValue({
    ...resultVersion,
    analysis_context: "user_feedback",
  });
  apiMock.classificationResultRecordGroups.mockResolvedValue({
    items: [
      groupOf({
        ...record,
        reason: "Great winter gloves",
        comment: "Warm and comfortable",
        problem_labels: [],
        classification: {
          ...record.classification,
          primary_label_codes: [],
          problem_label_codes: [],
          positive_label_codes: ["COMFORT_POSITIVE"],
        },
      }),
    ],
    total: 1,
    source_total: 1,
    page: 1,
    page_size: 20,
  });
  window.location.hash =
    "classification-results?result_version_id=classification-version-1";

  render(<ClassificationResultsPage notify={vi.fn()} />);

  const section = (await screen.findByText("用户反馈记录")).closest("section");
  expect(within(section).queryByText(/组反馈 · 关联/)).not.toBeInTheDocument();
  expect(
    within(section).queryByText(/重跑标记仅表示当前版本的需求/),
  ).not.toBeInTheDocument();
  expect(within(section).getByText("反馈标题 / 正文")).toBeVisible();
  expect(within(section).getByText("Great winter gloves")).toBeVisible();
  expect(within(section).getByText("Warm and comfortable")).toBeVisible();

  await user.click(within(section).getByRole("button", { name: "查看证据" }));
  const drawer = screen.getByRole("dialog", { name: "分类结果与证据" });
  expect(within(drawer).getByText("用户反馈原文")).toBeVisible();
  expect(within(drawer).getByText("反馈标题")).toBeVisible();
  await userEvent.click(
    within(drawer).getByText("业务标签与记录状态", { selector: "summary" }),
  );
  expect(within(drawer).getByText("正向标签")).toBeVisible();
  expect(within(drawer).queryByText("Amazon原因")).not.toBeInTheDocument();
});

test("同一反馈只显示一份结论并可展开两条源明细", async () => {
  const user = userEvent.setup();
  apiMock.classificationResultRecordGroups.mockResolvedValue({
    items: [
      {
        record,
        member_count: 2,
        members: [
          groupOf(record).members[0],
          {
            source_record_id: "returns-v3:3",
            source_row: 3,
            return_date: "2026-08-02",
            reason: "TOO_SMALL",
            comment: "Too small for me",
          },
        ],
      },
    ],
    total: 1,
    source_total: 2,
    page: 1,
    page_size: 20,
  });
  window.location.hash =
    "classification-results?result_version_id=classification-version-1";

  render(<ClassificationResultsPage notify={vi.fn()} />);
  const section = (await screen.findByText("订单级分类记录")).closest("section");
  expect(within(section).getByText("共 1 条")).toBeVisible();
  expect(within(section).getAllByText("ORDER-001")).toHaveLength(1);
  await user.click(within(section).getByRole("button", { name: "查看证据" }));
  const drawer = screen.getByRole("dialog", { name: "分类结果与证据" });
  expect(within(drawer).getByText("关联源明细（2）")).toBeVisible();
  expect(within(drawer).getByText("源记录 2 · 2026-08-01")).toBeVisible();
  expect(within(drawer).getByText("源记录 3 · 2026-08-02")).toBeVisible();
  expect(within(drawer).getAllByText("业务标签与记录状态")).toHaveLength(1);
});

test("业务下钻按反馈组显示数量", async () => {
  apiMock.classificationResultRecordGroups.mockResolvedValue({
    items: [{ ...groupOf(record), member_count: 2 }],
    total: 1,
    source_total: 2,
    page: 1,
    page_size: 20,
  });
  window.location.hash =
    "classification-results?result_version_id=classification-version-1";

  render(<ClassificationResultsPage notify={vi.fn()} />);

  expect(await screen.findByRole("button", { name: /偏小\s*1\s*组/ })).toBeVisible();
  expect(screen.getByRole("button", { name: /产品表权威名称\s*1\s*组/ })).toBeVisible();
  expect(screen.getByText("共 1 条")).toBeVisible();
});

afterEach(() => cleanup());

test("结果池使用服务端筛选并展示多产品名称", async () => {
  const user = userEvent.setup();
  window.location.hash =
    "classification-results?record_page=4&problem=STALE&product_name=STALE";
  render(<ClassificationResultsPage notify={vi.fn()} />);

  expect(await screen.findByText("产品表权威名称")).toBeVisible();
  expect(screen.getByText("另有 1 个产品名称")).toBeVisible();
  const filters = screen.getByRole("region", { name: "分类结果筛选" });
  for (const label of ["关键词", "店铺/站点", "Listing", "记录情况"]) {
    expect(within(filters).getByText(label, { selector: "span" })).toBeVisible();
  }

  await user.type(screen.getByRole("textbox", { name: "搜索分类结果" }), "水鞋");
  const qualitySelect = screen.getByRole("combobox", { name: "记录情况" });
  fireEvent.mouseDown(
    qualitySelect.closest(".ant-select").querySelector(".ant-select-content"),
  );
  await user.click(
    await screen.findByText("含待复核记录", {
      selector: ".ant-select-item-option-content",
    }),
  );
  await user.click(screen.getByRole("button", { name: "筛选" }));

  await waitFor(() =>
    expect(apiMock.classificationResults).toHaveBeenLastCalledWith(
      expect.objectContaining({
        q: "水鞋",
        page: 1,
        page_size: 20,
        quality_status: "review_required",
      }),
      expect.any(Object),
    ),
  );
  expect(window.location.hash).toContain("q=%E6%B0%B4%E9%9E%8B");
  expect(window.location.hash).toContain("quality_status=review_required");

  await user.click(screen.getByRole("button", { name: "SR001" }));
  await waitFor(() =>
    expect(window.location.hash).toContain(
      "result_version_id=classification-version-1",
    ),
  );
  expect(window.location.hash).not.toContain("record_page");
  expect(window.location.hash).not.toContain("problem=STALE");
  expect(window.location.hash).not.toContain("product_name=STALE");
});

test("看板选择允许需复核版本并明确按可用范围统计", async () => {
  const derived = {
    ...resultVersion,
    version_id: "classification-version-derived",
    version: 2,
    listing: "DERIVED",
    delivery_status: "review-derived",
    publish_origin: "review-derived",
    dashboard_eligibility: true,
  };
  const needsReview = {
    ...resultVersion,
    version_id: "classification-version-review",
    listing: "REVIEW",
    delivery_status: "needs_review",
    dashboard_eligibility: true,
    blocking_reasons: [],
  };
  const blocked = {
    ...resultVersion,
    version_id: "classification-version-blocked",
    listing: "BLOCKED",
    quality_status: "unusable",
    delivery_status: "unusable",
    dashboard_eligibility: false,
    blocking_reasons: [{ message: "分类结果不可用于看板" }],
  };
  apiMock.classificationResults.mockResolvedValue({
    items: [derived, needsReview, blocked],
    total: 3,
    page: 1,
    page_size: 20,
  });
  render(<ClassificationResultsPage notify={vi.fn()} userId="user-1" />);

  expect(await screen.findByRole("button", { name: "新建分析看板" })).toBeDisabled();
  await userEvent.click(
    await screen.findByRole("checkbox", { name: "选择 DERIVED 结果 v2" }),
  );
  expect(screen.getByRole("checkbox", { name: "选择 DERIVED 结果 v2" })).toBeEnabled();
  expect(screen.getByRole("checkbox", { name: "选择 REVIEW 结果 v1" })).toBeEnabled();
  const blockedCheckbox = screen.getByRole("checkbox", {
    name: "选择 BLOCKED 结果 v1",
  });
  expect(blockedCheckbox).toBeEnabled();
  expect(screen.queryByText("分类结果不可用于看板")).not.toBeInTheDocument();
  expect(screen.getByText(/统计范围可在确认时调整/)).toBeVisible();
});

test("从分类结果快速确认并创建 AI 洞察报告任务", async () => {
  const user = userEvent.setup();
  const notify = vi.fn();
  sessionStorage.clear();
  render(<ResultCreationHarness notify={notify} />);

  const selectionCheckbox = await screen.findByRole("checkbox", {
    name: "选择 SR001 结果 v1",
  });
  const selectionCell = selectionCheckbox.closest("label.result-selection-cell");
  expect(selectionCell).toBeVisible();
  await user.click(selectionCell);
  expect(selectionCheckbox).toBeChecked();
  expect(screen.getByText("已选 1 个结果版本")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "生成 AI 洞察" }));

  const dialog = await screen.findByRole("dialog", {
    name: "生成 AI 洞察报告",
  });
  expect(within(dialog).getByLabelText("模型")).toHaveDisplayValue(
    "GPT-5.6 · OpenAI 主接入",
  );
  expect(within(dialog).getByText(/待处理 1 条.*已忽略 1 条/)).toBeVisible();
  expect(within(dialog).getByRole("button", { name: "高" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  await user.click(within(dialog).getByRole("button", { name: "开始生成" }));
  await waitFor(() =>
    expect(dashboardApiMock.createInsightReportFromResults).toHaveBeenCalledWith({
      result_version_ids: ["classification-version-1"],
      filters: {},
      plan_hash: "plan-ai-insight",
      model_id: "model-1",
      reasoning_effort: "high",
    }),
  );
  expect(notify).toHaveBeenCalledWith("AI 洞察报告已加入生成队列");
  expect(
    screen.queryByRole("dialog", { name: "生成 AI 洞察报告" }),
  ).not.toBeInTheDocument();
  expect(window.location.hash).toContain("dashboard=dashboard-ai-insight");
  expect(window.location.hash).toContain("version=dashboard-version-ai-insight");
  expect(window.location.hash).toContain("tab=report");
  expect(window.location.hash).toContain("report=report-ai-insight");
});

test("从第二页首次勾选结果不改变当前页码", async () => {
  window.location.hash = "classification-results?page=2";
  apiMock.classificationResults.mockResolvedValue({
    items: [resultVersion],
    total: 21,
    page: 2,
    page_size: 20,
  });
  render(<ResultCreationHarness />);
  await userEvent.click(
    await screen.findByRole("checkbox", { name: "选择 SR001 结果 v1" }),
  );
  expect(new URLSearchParams(window.location.hash.split("?")[1]).get("page")).toBe("2");
});

test("两个创建入口共用跨页选择，取消后保留看板草稿", async () => {
  const user = userEvent.setup();
  window.location.hash =
    "classification-results?q=合成筛选&store_site=SEEKWAY%3AUS&quality_status=review_required";
  apiMock.classificationResults.mockResolvedValue({
    items: [resultVersion],
    total: 21,
    page: 1,
    page_size: 20,
  });
  render(<ResultCreationHarness />);
  expect(screen.getByRole("button", { name: "新建分析看板" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "生成 AI 洞察" })).toBeDisabled();
  await user.click(await screen.findByRole("checkbox", { name: "选择 SR001 结果 v1" }));
  const token = new URLSearchParams(window.location.hash.split("?")[1]).get(
    "selection_token",
  );
  apiMock.classificationResults.mockResolvedValue({
    items: [
      { ...resultVersion, version_id: "classification-version-2", listing: "SR002" },
    ],
    total: 21,
    page: 2,
    page_size: 20,
  });
  await user.click(screen.getByRole("button", { name: "下一页" }));
  await user.click(await screen.findByRole("checkbox", { name: "选择 SR002 结果 v1" }));
  expect(screen.getByText("已选 2 个结果版本")).toBeVisible();
  expect(screen.queryByRole("button", { name: "检查并生成" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "新建分析看板" }));
  await user.type(await screen.findByLabelText("看板名称"), "每周反馈看板");
  await user.click(screen.getByRole("button", { name: /返回选择分类结果/ }));
  expect(await screen.findByText("已选 2 个结果版本")).toBeVisible();
  const restoredQuery = new URLSearchParams(window.location.hash.split("?")[1]);
  expect(restoredQuery.get("q")).toBe("合成筛选");
  expect(restoredQuery.get("store_site")).toBe("SEEKWAY:US");
  expect(restoredQuery.get("quality_status")).toBe("review_required");
  expect(restoredQuery.get("page")).toBe("2");
  await user.click(screen.getByRole("button", { name: "新建分析看板" }));
  expect(await screen.findByLabelText("看板名称")).toHaveValue("每周反馈看板");
  await user.click(screen.getByRole("button", { name: /返回选择分类结果/ }));
  await user.click(await screen.findByRole("button", { name: "生成 AI 洞察" }));
  const dialog = await screen.findByRole("dialog", { name: "生成 AI 洞察报告" });
  await user.click(await within(dialog).findByRole("button", { name: "中" }));
  await user.click(within(dialog).getByRole("button", { name: "取消" }));
  expect(await screen.findByText("已选 2 个结果版本")).toBeVisible();
  const insightReturnedQuery = new URLSearchParams(window.location.hash.split("?")[1]);
  expect(insightReturnedQuery.get("q")).toBe("合成筛选");
  expect(insightReturnedQuery.get("store_site")).toBe("SEEKWAY:US");
  expect(insightReturnedQuery.get("quality_status")).toBe("review_required");
  expect(insightReturnedQuery.get("page")).toBe("2");
  expect(insightReturnedQuery.get("selection_token")).toBe(token);
  await user.click(screen.getByRole("button", { name: "生成 AI 洞察" }));
  const restored = await screen.findByRole("dialog", { name: "生成 AI 洞察报告" });
  expect(await within(restored).findByRole("button", { name: "中" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(readDashboardSelection("user-1", token).selected).toHaveLength(2);
  expect(dashboardApiMock.dashboardPreflight).toHaveBeenLastCalledWith(
    {
      result_version_ids: ["classification-version-1", "classification-version-2"],
      filters: {},
    },
    expect.any(Object),
  );
  await user.click(within(restored).getByRole("button", { name: "开始生成" }));
  await waitFor(() =>
    expect(dashboardApiMock.createInsightReportFromResults).toHaveBeenCalledWith(
      expect.objectContaining({
        result_version_ids: ["classification-version-1", "classification-version-2"],
        reasoning_effort: "medium",
      }),
    ),
  );
  expect(readDashboardSelection("user-1", token)).toBeNull();
});

test("AI 洞察处理版本冲突后仅提交选定版本，失败可重试", async () => {
  const user = userEvent.setup();
  apiMock.classificationResults.mockResolvedValue({
    items: [
      resultVersion,
      { ...resultVersion, version_id: "classification-version-2", version: 2 },
    ],
    total: 2,
    page: 1,
    page_size: 20,
  });
  dashboardApiMock.dashboardPreflight.mockImplementation(({ result_version_ids }) =>
    Promise.resolve({
      plan_hash: `plan-${result_version_ids.join("-")}`,
      ready: result_version_ids.length === 1,
      conflicts:
        result_version_ids.length === 2
          ? [{ store_site: "SEEKWAY:US", listing: "SR001", result_version_ids }]
          : [],
      summary: { record_count: 3 },
    }),
  );
  dashboardApiMock.createInsightReportFromResults.mockRejectedValueOnce(
    new Error("暂时无法提交"),
  );
  render(<ResultCreationHarness />);
  await user.click(await screen.findByRole("checkbox", { name: "选择 SR001 结果 v1" }));
  await user.click(screen.getByRole("checkbox", { name: "选择 SR001 结果 v2" }));
  await user.click(screen.getByRole("button", { name: "生成 AI 洞察" }));
  expect(await screen.findByText("同一 Listing 选择了多个结果版本")).toBeVisible();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /确认冲突选择/ }));
  expect(screen.getByText("请为每个冲突 Listing 选择一个结果版本。")).toBeVisible();
  await user.click(screen.getByRole("radio", { name: /结果 v2/ }));
  await user.click(screen.getByRole("button", { name: /确认冲突选择/ }));
  const dialog = await screen.findByRole("dialog", { name: "生成 AI 洞察报告" });
  await user.click(await within(dialog).findByRole("button", { name: "开始生成" }));
  expect(await within(dialog).findByText("暂时无法提交")).toBeVisible();
  expect(within(dialog).getByRole("button", { name: "开始生成" })).toBeEnabled();
  await user.click(within(dialog).getByRole("button", { name: "开始生成" }));
  await waitFor(() =>
    expect(dashboardApiMock.createInsightReportFromResults).toHaveBeenCalledTimes(2),
  );
  expect(dashboardApiMock.createInsightReportFromResults).toHaveBeenLastCalledWith(
    expect.objectContaining({
      result_version_ids: ["classification-version-2"],
      plan_hash: "plan-classification-version-2",
    }),
  );
});

test("旧看板选择会话恢复为当前创建流程，清空后禁用创建", async () => {
  const { createDashboardSelection } =
    await import("../src/features/analysis-dashboards/dashboardSelectionStorage");
  const token = createDashboardSelection("user-1", {
    target_dashboard_id: "existing-dashboard",
    expected_revision: 3,
  });
  window.location.hash = `#classification-results?selection_token=${token}`;
  const user = userEvent.setup();
  render(<ResultCreationHarness />);
  await user.click(await screen.findByRole("checkbox", { name: "选择 SR001 结果 v1" }));
  expect(screen.getByRole("button", { name: "生成 AI 洞察" })).toBeEnabled();
  expect(readDashboardSelection("user-1", token)).not.toHaveProperty(
    "target_dashboard_id",
  );
  expect(readDashboardSelection("user-1", token)).not.toHaveProperty(
    "expected_revision",
  );
  await user.click(screen.getByRole("button", { name: "新建分析看板" }));
  expect(await screen.findByRole("heading", { name: "创建分析看板" })).toBeVisible();
  expect(screen.queryByLabelText("版本原因")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /返回选择分类结果/ }));
  await user.click(await screen.findByRole("button", { name: "清空" }));
  expect(screen.getByRole("button", { name: "新建分析看板" })).toBeDisabled();
});

test("AI 提交期间防止重复操作，计划过期后保留参数并再次确认", async () => {
  const user = userEvent.setup();
  const expired = new Error("计划已过期");
  expired.status = 409;
  let rejectSubmission;
  dashboardApiMock.createInsightReportFromResults.mockImplementationOnce(
    () =>
      new Promise((_resolve, reject) => {
        rejectSubmission = reject;
      }),
  );
  dashboardApiMock.dashboardPreflight
    .mockResolvedValueOnce({
      ready: true,
      plan_hash: "old-plan",
      summary: { record_count: 3 },
    })
    .mockResolvedValue({
      ready: true,
      plan_hash: "new-plan",
      summary: { record_count: 3 },
    });
  render(<ResultCreationHarness />);
  await user.click(await screen.findByRole("checkbox", { name: "选择 SR001 结果 v1" }));
  await user.click(screen.getByRole("button", { name: "生成 AI 洞察" }));
  const dialog = await screen.findByRole("dialog", { name: "生成 AI 洞察报告" });
  await user.click(await within(dialog).findByRole("button", { name: "中" }));
  await user.dblClick(within(dialog).getByRole("button", { name: "开始生成" }));
  expect(dashboardApiMock.createInsightReportFromResults).toHaveBeenCalledTimes(1);
  expect(within(dialog).getByRole("button", { name: "正在提交…" })).toBeDisabled();
  expect(within(dialog).getByRole("button", { name: "取消" })).toBeDisabled();
  await user.keyboard("{Escape}");
  expect(dialog).toBeVisible();
  await act(async () => rejectSubmission(expired));
  const refreshed = await screen.findByRole("dialog", { name: "生成 AI 洞察报告" });
  expect(await within(refreshed).findByText(/已保留模型选择并重新检查/)).toBeVisible();
  expect(within(refreshed).getByRole("button", { name: "中" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(within(refreshed).getByRole("button", { name: "开始生成" })).toBeEnabled();
  await user.click(within(refreshed).getByRole("button", { name: "开始生成" }));
  await waitFor(() =>
    expect(dashboardApiMock.createInsightReportFromResults).toHaveBeenCalledTimes(2),
  );
  expect(dashboardApiMock.createInsightReportFromResults).toHaveBeenLastCalledWith(
    expect.objectContaining({
      plan_hash: "new-plan",
      reasoning_effort: "medium",
    }),
  );
});

test("刷新恢复产品名称下钻且切换产品不会混入其他订单", async () => {
  const user = userEvent.setup();
  const secondRecord = {
    ...record,
    source_record_id: "returns-v3:3",
    source_row: 3,
    order_id: "ORDER-002",
    product_name: "产品表第二名称",
    product_sku: "PRODUCT-SKU-2",
  };
  apiMock.classificationResultRecordGroups.mockImplementation((_versionId, filters) => {
    const selected = filters.product_name === "产品表第二名称" ? secondRecord : record;
    return Promise.resolve({
      items: [groupOf(selected)],
      total: 1,
      source_total: 1,
      page: filters.page,
      page_size: filters.page_size,
    });
  });
  apiMock.classificationResultDrilldown.mockImplementation(
    (_versionId, groupBy, filters) => {
      const values = {
        problem: [
          {
            value: "FIT_TOO_SMALL",
            label_name: "偏小",
            record_count: 3,
            unit_count: 1,
          },
        ],
        product_name: [
          { value: "产品表权威名称", record_count: 2, unit_count: 1 },
          { value: "产品表第二名称", record_count: 1, unit_count: 1 },
        ],
        product_sku: [
          {
            value:
              filters.product_name === "产品表第二名称"
                ? "PRODUCT-SKU-2"
                : "PRODUCT-SKU-1",
            record_count: 1,
            unit_count: 1,
          },
        ],
      };
      return Promise.resolve({
        group_by: groupBy,
        items: values[groupBy],
        total: values[groupBy].length,
        page: 1,
        page_size: 100,
      });
    },
  );
  window.location.hash =
    "classification-results?version=classification-version-1&record_page=3&problem=FIT_TOO_SMALL&product_name=%E4%BA%A7%E5%93%81%E8%A1%A8%E6%9D%83%E5%A8%81%E5%90%8D%E7%A7%B0&product_sku=PRODUCT-SKU-1";

  render(<ClassificationResultsPage notify={vi.fn()} />);

  expect(await screen.findByText("SR001 分类结果")).toBeVisible();
  await waitFor(() =>
    expect(apiMock.classificationResultRecordGroups).toHaveBeenCalledWith(
      "classification-version-1",
      expect.objectContaining({
        page: 3,
        problem: "FIT_TOO_SMALL",
        product_name: "产品表权威名称",
        product_sku: "PRODUCT-SKU-1",
      }),
      expect.any(Object),
    ),
  );

  const recordSection = screen.getByText("订单级分类记录").closest("section");
  expect(within(recordSection).getByText("ORDER-001")).toBeVisible();
  expect(within(recordSection).queryByText("ORDER-002")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /产品表第二名称/ }));
  await waitFor(() =>
    expect(apiMock.classificationResultRecordGroups).toHaveBeenLastCalledWith(
      "classification-version-1",
      expect.objectContaining({
        page: 1,
        product_name: "产品表第二名称",
        product_sku: "",
      }),
      expect.any(Object),
    ),
  );
  expect(window.location.hash).not.toContain("record_page");
  expect(window.location.hash).toContain(
    "product_name=%E4%BA%A7%E5%93%81%E8%A1%A8%E7%AC%AC%E4%BA%8C%E5%90%8D%E7%A7%B0",
  );
  expect(await within(recordSection).findByText("ORDER-002")).toBeVisible();
  expect(within(recordSection).queryByText("ORDER-001")).not.toBeInTheDocument();

  const evidenceTrigger = await screen.findByRole("button", { name: "查看证据" });
  await user.click(evidenceTrigger);
  const drawer = screen.getByRole("dialog", { name: "分类结果与证据" });
  const closeButton = within(drawer).getByRole("button", {
    name: "关闭证据抽屉",
  });
  const semanticSummary = drawer.querySelector(".semantic-conclusion-item > summary");
  expect(semanticSummary).not.toBeNull();
  expect(closeButton).toHaveFocus();
  await user.tab();
  expect(screen.getByRole("button", { name: "人工修正" })).toHaveFocus();
  await user.tab();
  expect(semanticSummary).toHaveFocus();
  closeButton.focus();
  await user.tab({ shift: true });
  expect(within(drawer).getByText("运行来源", { selector: "summary" })).toHaveFocus();
  await user.tab();
  expect(closeButton).toHaveFocus();
  await user.click(within(drawer).getByText("业务信息", { selector: "summary" }));
  expect(within(drawer).getByText("产品表第二名称")).toBeVisible();
  expect(within(drawer).getAllByText("SOURCE-MSKU-1")).toHaveLength(2);
  expect(within(drawer).getByText("PRODUCT-SKU-2")).toBeVisible();
  expect(within(drawer).getAllByText("Too small", { exact: false })).toHaveLength(2);
  expect(within(drawer).queryByText("绝不可作为产品名称")).not.toBeInTheDocument();
  await user.keyboard("{Escape}");
  expect(
    screen.queryByRole("dialog", { name: "分类结果与证据" }),
  ).not.toBeInTheDocument();
  expect(evidenceTrigger).toHaveFocus();
});

test("需复核且没有问题标签时以复核为主操作并说明订单现状", async () => {
  const needsReview = {
    ...resultVersion,
    record_count: 318,
    quality_status: "review_required",
    delivery_status: "needs_review",
    dashboard_eligibility: false,
    blocking_reasons: [
      { code: "needs_review", message: "分类结果必须先完成复核并发布派生版本" },
    ],
  };
  apiMock.classificationResult.mockResolvedValue(needsReview);
  apiMock.classificationResultVersions.mockResolvedValue([needsReview]);
  apiMock.classificationResultSummary.mockResolvedValue({
    quality: [{ quality_status: "review_required", record_count: 318, unit_count: 10 }],
  });
  apiMock.classificationResultRecordGroups.mockResolvedValue({
    items: [],
    total: 0,
    source_total: 0,
    page: 1,
    page_size: 20,
  });
  apiMock.classificationResultDrilldown.mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 100,
  });
  window.location.hash =
    "classification-results?result_version_id=classification-version-1&task_id=task-1&segment_id=segment-1";

  render(<ClassificationResultsPage notify={vi.fn()} />);

  expect(await screen.findByRole("heading", { name: "SR001 分类结果" })).toBeVisible();
  expect(screen.getByRole("button", { name: "创建分析看板" })).toBeEnabled();
  expect(
    screen.queryByRole("button", { name: "基于此版本创建看板" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByText("尚未形成问题标签；当前 318 条均需复核，可在查看证据时人工修正。"),
  ).toBeVisible();
  const problemColumn = screen.getByText("问题").closest(".drilldown-column");
  expect(within(problemColumn).getByText("尚未形成问题标签")).toBeVisible();
  expect(
    within(problemColumn).getByText("当前 318 条记录需复核，可在查看证据时人工修正。"),
  ).toBeVisible();
  expect(within(problemColumn).queryByText("暂无数据")).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "修改历史" }));
  expect(
    screen.queryByRole("button", { name: "创建复核批次" }),
  ).not.toBeInTheDocument();
  expect(window.location.hash).toContain("task_id=task-1");
  expect(window.location.hash).toContain("segment_id=segment-1");
});

test("真正没有记录时问题栏保持通用空态", async () => {
  const emptyResult = {
    ...resultVersion,
    record_count: 0,
    unit_count: 0,
  };
  apiMock.classificationResult.mockResolvedValue(emptyResult);
  apiMock.classificationResultSummary.mockResolvedValue({
    quality: [],
  });
  apiMock.classificationResultRecordGroups.mockResolvedValue({
    items: [],
    total: 0,
    source_total: 0,
    page: 1,
    page_size: 20,
  });
  apiMock.classificationResultDrilldown.mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 100,
  });
  window.location.hash =
    "classification-results?result_version_id=classification-version-1";

  render(<ClassificationResultsPage notify={vi.fn()} />);

  expect(await screen.findByRole("heading", { name: "SR001 分类结果" })).toBeVisible();
  const problemColumn = screen.getByText("问题").closest(".drilldown-column");
  expect(within(problemColumn).getByText("暂无数据")).toBeVisible();
  expect(within(problemColumn).queryByText("尚未形成问题标签")).not.toBeInTheDocument();
});

test("复核派生结果显示明确状态、主操作和看板次操作", async () => {
  const derived = {
    ...resultVersion,
    version_id: "classification-version-2",
    version: 2,
    delivery_status: "review-derived",
    publish_origin: "review-derived",
    dashboard_eligibility: true,
  };
  apiMock.classificationResult.mockResolvedValue(derived);
  window.location.hash =
    "classification-results?result_version_id=classification-version-2";

  render(<ClassificationResultsPage notify={vi.fn()} userId="user-1" />);

  expect(await screen.findByRole("heading", { name: "SR001 分类结果" })).toBeVisible();
  expect(screen.queryByText("复核已发布")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "查看衍生版本" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "创建分析看板" })).toBeEnabled();
});

test("结果池区分初始空状态和接口错误", async () => {
  apiMock.classificationResults.mockResolvedValueOnce({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
  });
  const { unmount } = render(<ClassificationResultsPage notify={vi.fn()} />);
  expect(await screen.findByText("结果池还是空的")).toBeVisible();
  unmount();

  apiMock.classificationResults.mockRejectedValueOnce(new Error("服务暂不可用"));
  render(<ClassificationResultsPage notify={vi.fn()} />);
  expect(await screen.findByText("分类结果读取失败")).toBeVisible();
  expect(screen.getByText("服务暂不可用")).toBeVisible();
});

test("不存在的分类结果详情支持页面内局部重试", async () => {
  const notify = vi.fn();
  apiMock.classificationResult
    .mockRejectedValueOnce(new Error("分类结果不存在"))
    .mockResolvedValueOnce(resultVersion);
  window.location.hash =
    "classification-results?result_version_id=missing-classification-version";

  render(<ClassificationResultsPage notify={notify} />);

  expect(await screen.findByText("分类结果读取失败")).toBeVisible();
  expect(screen.getByText("分类结果不存在")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "重试" }));
  expect(await screen.findByRole("heading", { name: "SR001 分类结果" })).toBeVisible();
  expect(apiMock.classificationResult).toHaveBeenCalledTimes(2);
  expect(notify).not.toHaveBeenCalled();
});

test("结果池在页面隐藏时暂停自动刷新", async () => {
  vi.useFakeTimers();
  Object.defineProperty(document, "hidden", { configurable: true, value: true });
  try {
    render(<ClassificationResultsPage notify={vi.fn()} />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(apiMock.classificationResults).toHaveBeenCalledTimes(1);

    await act(async () => vi.advanceTimersByTimeAsync(60100));
    expect(apiMock.classificationResults).toHaveBeenCalledTimes(1);
  } finally {
    Object.defineProperty(document, "hidden", { configurable: true, value: false });
    vi.useRealTimers();
  }
});

test("旧筛选刷新晚返回不会覆盖当前列表", async () => {
  vi.useFakeTimers();
  let emptyQueryCalls = 0;
  let oldPollSignal;
  let resolveOldPoll;
  const oldPoll = new Promise((resolve) => {
    resolveOldPoll = resolve;
  });
  const filteredVersion = {
    ...resultVersion,
    version_id: "classification-version-filtered",
    product_names: ["新筛选产品"],
  };
  apiMock.classificationResults.mockImplementation((filters, options = {}) => {
    if (filters.q === "新筛选") {
      return Promise.resolve({
        items: [filteredVersion],
        total: 1,
        page: 1,
        page_size: 20,
      });
    }
    emptyQueryCalls += 1;
    if (emptyQueryCalls === 1) {
      return Promise.resolve({
        items: [resultVersion],
        total: 1,
        page: 1,
        page_size: 20,
      });
    }
    oldPollSignal = options.signal;
    return oldPoll;
  });

  try {
    render(<ClassificationResultsPage notify={vi.fn()} />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByText("产品表权威名称")).toBeVisible();

    await act(async () => {
      vi.advanceTimersByTime(60100);
      await Promise.resolve();
    });
    expect(oldPollSignal).toBeDefined();

    fireEvent.change(screen.getByRole("textbox", { name: "搜索分类结果" }), {
      target: { value: "新筛选" },
    });
    fireEvent.click(screen.getByRole("button", { name: "筛选" }));
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(oldPollSignal.aborted).toBe(true);
    expect(screen.getByText("新筛选产品")).toBeVisible();

    await act(async () => {
      resolveOldPoll({
        items: [
          {
            ...resultVersion,
            version_id: "classification-version-stale-new",
            product_names: ["旧筛选迟到结果"],
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
      });
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByText("新筛选产品")).toBeVisible();
    expect(screen.queryByText("旧筛选迟到结果")).not.toBeInTheDocument();
    expect(
      screen.queryByText("有新的 Listing 分类结果可用，当前列表未自动改变。"),
    ).not.toBeInTheDocument();
  } finally {
    cleanup();
    vi.useRealTimers();
  }
});

test("版本历史显示真实派生链且历史版本主动作进入最新版本", async () => {
  const derived = {
    ...resultVersion,
    version_id: "classification-version-2",
    version: 2,
    created_by_name: "复核员乙",
    parent_version_id: resultVersion.version_id,
    parent_version_no: 1,
    source_review_batch_id: "review-batch-1",
    changed_unit_count: 2,
    inherited_unit_count: 1,
    version_reason: "人工复核后发布",
    created_at: "2026-08-12T10:00:00Z",
  };
  apiMock.classificationResultVersions.mockResolvedValue([
    {
      ...resultVersion,
      created_by_name: null,
      version_reason: "首次分类发布",
    },
    derived,
  ]);
  window.location.hash =
    "classification-results?result_version_id=classification-version-1&tab=history";

  render(<ClassificationResultsPage notify={vi.fn()} />);

  expect(await screen.findByText("v1 · 原始分类")).toBeVisible();
  expect(screen.getByText("v2 · 历史批次复核")).toBeVisible();
  expect(screen.getByText("人工复核后发布")).toBeVisible();
  expect(screen.getByText("操作者信息未提供", { exact: false })).toBeVisible();
  expect(screen.getByText("复核员乙", { exact: false })).toBeVisible();
  expect(
    screen.getByText("基于 v1 修改 2 个分类单元，其余 1 个沿用来源版本"),
  ).toBeVisible();
  expect(screen.getByText("复核批次：review-batch-1")).toBeInTheDocument();
  expect(apiMock.classificationResultRecordGroups).not.toHaveBeenCalled();
  expect(apiMock.classificationResultDrilldown).not.toHaveBeenCalled();

  await userEvent.click(screen.getByRole("button", { name: "查看修改记录" }));
  expect(window.location.hash).toContain("result_version_id=classification-version-2");
  expect(window.location.hash).toContain("tab=history");
});

test("派生统计字段缺失时只显示已有记录与分类单元摘要", async () => {
  const derived = {
    ...resultVersion,
    version_id: "classification-version-2",
    version: 2,
    parent_version_id: resultVersion.version_id,
    parent_version_no: null,
    changed_unit_count: null,
    inherited_unit_count: null,
  };
  apiMock.classificationResultVersions.mockResolvedValue([resultVersion, derived]);
  window.location.hash =
    "classification-results?result_version_id=classification-version-1&tab=history";

  render(<ClassificationResultsPage notify={vi.fn()} />);

  expect(await screen.findByText("v2 · 分析结果更新")).toBeVisible();
  expect(screen.queryByText(/修改 .* 个分类单元/)).not.toBeInTheDocument();
  expect(screen.getAllByText(/3 条记录 · 1 个分类单元/)).toHaveLength(2);
});

test("修改历史更新中和更新失败均保留已有条目", async () => {
  const props = {
    history: [resultVersion],
    resultVersionId: resultVersion.version_id,
    loading: false,
    error: "",
    onReload: vi.fn(),
    onSelectVersion: vi.fn(),
  };
  const view = render(<ResultVersionHistory {...props} />);
  view.rerender(<ResultVersionHistory {...props} loading />);
  expect(screen.getByText("v1 · 原始分类")).toBeVisible();
  view.rerender(<ResultVersionHistory {...props} error="合成历史失败" />);
  expect(screen.getByText("合成历史失败")).toBeVisible();
  expect(screen.getByText("v1 · 原始分类")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "重新加载" }));
  expect(props.onReload).toHaveBeenCalledOnce();
});

test("复核版本切换取消共享旧请求，晚返回不覆盖新历史且卸载取消新请求", async () => {
  let finishOld;
  const oldHistory = new Promise((resolve) => {
    finishOld = resolve;
  });
  const nextVersion = {
    ...resultVersion,
    version_id: "synthetic-version-2",
    version: 2,
  };
  apiMock.classificationResultVersions.mockImplementation((id) =>
    id === resultVersion.version_id ? oldHistory : Promise.resolve([nextVersion]),
  );
  const props = { onSelectVersion: vi.fn(), notify: vi.fn() };
  const view = render(<ResultVersionReviewPanel result={resultVersion} {...props} />);
  const oldSignal = apiMock.classificationResultVersions.mock.calls[0][1].signal;

  view.rerender(<ResultVersionReviewPanel result={nextVersion} {...props} />);
  expect(await screen.findByText("v2 · 分析结果更新")).toBeVisible();
  expect(oldSignal.aborted).toBe(true);
  const nextSignal = apiMock.classificationResultVersions.mock.calls[1][1].signal;

  await act(async () => finishOld([resultVersion]));
  expect(screen.queryByText("v1 · 原始分类")).not.toBeInTheDocument();
  expect(screen.getByText("v2 · 分析结果更新")).toBeVisible();
  expect(apiMock.classificationResultVersions).toHaveBeenCalledTimes(2);
  expect(apiMock.reviewBatches).not.toHaveBeenCalled();
  view.unmount();
  expect(nextSignal.aborted).toBe(true);
});

import { classificationResultRouteState } from "../src/features/classification-results/classificationResultRoute";
import { useClassificationResultDetailData } from "../src/features/classification-results/useClassificationResultDetailData";

function ResultResourceProbe({ route, notify }) {
  const state = useClassificationResultDetailData({ route, notify });
  return (
    <div>
      <output aria-label="概况版本">{state.result?.version_id || ""}</output>
      <output aria-label="记录总数">{state.records?.total ?? 0}</output>
      <output aria-label="记录加载">{String(state.recordsLoading)}</output>
      <output aria-label="概况错误">{state.error}</output>
      <button onClick={state.retry}>重试概况</button>
    </div>
  );
}

test("详情资源切换筛选后忽略迟到记录并保持概况请求去重", async () => {
  const notify = vi.fn();
  let resolveOld;
  const oldRequest = new Promise((resolve) => {
    resolveOld = resolve;
  });
  apiMock.classificationResultRecordGroups.mockReturnValueOnce(oldRequest);
  apiMock.classificationResultRecordGroups.mockResolvedValue({ items: [], total: 7 });
  const route = classificationResultRouteState({
    result_version_id: resultVersion.version_id,
  });
  const { rerender } = render(<ResultResourceProbe route={route} notify={notify} />);
  await waitFor(() =>
    expect(screen.getByLabelText("概况版本")).toHaveTextContent(
      resultVersion.version_id,
    ),
  );
  const firstSignal = apiMock.classificationResultRecordGroups.mock.calls[0][2].signal;
  rerender(
    <ResultResourceProbe
      route={{ ...route, productName: "合成筛选商品" }}
      notify={notify}
    />,
  );
  await waitFor(() => expect(screen.getByLabelText("记录总数")).toHaveTextContent("7"));
  expect(firstSignal.aborted).toBe(true);
  expect(apiMock.classificationResult).toHaveBeenCalledTimes(1);
  expect(apiMock.classificationResultSummary).toHaveBeenCalledTimes(1);
  expect(apiMock.classificationResultRecordGroups).toHaveBeenCalledTimes(2);
  expect(apiMock.classificationResultDrilldown).toHaveBeenCalledTimes(6);
  await act(async () => {
    resolveOld({ items: [], total: 2 });
    await oldRequest;
  });
  expect(screen.getByLabelText("记录总数")).toHaveTextContent("7");
  expect(screen.getByLabelText("概况错误")).toBeEmptyDOMElement();
  expect(notify).not.toHaveBeenCalled();
});

test("历史页不请求记录且下钻失败不影响概况重试", async () => {
  const notify = vi.fn();
  const route = classificationResultRouteState({
    result_version_id: resultVersion.version_id,
    tab: "history",
  });
  const { rerender } = render(<ResultResourceProbe route={route} notify={notify} />);
  await waitFor(() =>
    expect(screen.getByLabelText("概况版本")).toHaveTextContent(
      resultVersion.version_id,
    ),
  );
  expect(screen.getByLabelText("记录加载")).toHaveTextContent("false");
  expect(apiMock.classificationResultRecordGroups).not.toHaveBeenCalled();
  expect(apiMock.classificationResultDrilldown).not.toHaveBeenCalled();
  apiMock.classificationResultRecordGroups.mockRejectedValueOnce(
    new Error("合成下钻读取失败"),
  );
  rerender(
    <ResultResourceProbe route={{ ...route, tab: "records" }} notify={notify} />,
  );
  await waitFor(() => expect(notify).toHaveBeenCalledWith("合成下钻读取失败", "error"));
  expect(screen.getByLabelText("概况版本")).toHaveTextContent(resultVersion.version_id);
  expect(screen.getByLabelText("概况错误")).toBeEmptyDOMElement();
  fireEvent.click(screen.getByRole("button", { name: "重试概况" }));
  await waitFor(() => expect(apiMock.classificationResult).toHaveBeenCalledTimes(2));
  expect(apiMock.classificationResultSummary).toHaveBeenCalledTimes(2);
  expect(apiMock.classificationResultRecordGroups).toHaveBeenCalledTimes(1);
  expect(apiMock.classificationResultDrilldown).toHaveBeenCalledTimes(3);
});

test("结果池更新失败保留已有版本和重试入口", async () => {
  const { ResultPoolContent } =
    await import("../src/features/classification-results/ResultPoolContent");
  const load = vi.fn();
  render(
    <ResultPoolContent
      data={{ items: [resultVersion], total: 1 }}
      route={{ page: 1, pageSize: 20 }}
      selectedIds={new Set()}
      loading={false}
      error="连接中断"
      load={load}
      updateRoute={vi.fn()}
      toggleSelection={vi.fn()}
      runPrimaryAction={vi.fn()}
      totalPages={1}
      changePage={vi.fn()}
      changePageSize={vi.fn()}
    />,
  );
  expect(screen.getByText("分类结果更新失败，当前显示上一次数据")).toBeVisible();
  const table = screen.getByRole("table", { name: "分类结果" });
  expect(within(table).getByText("SR001")).toBeVisible();
  expect(within(table).getAllByRole("columnheader")).toHaveLength(7);
  expect(within(table).getAllByRole("cell")).toHaveLength(7);
  await userEvent.click(screen.getByRole("button", { name: "重试", exact: true }));
  expect(load).toHaveBeenCalledOnce();
});

test("结果池筛选为空时清除条件并返回第一页", async () => {
  const { ResultPoolStatus } =
    await import("../src/features/classification-results/ResultPoolStatus");
  const updateRoute = vi.fn();
  render(
    <ResultPoolStatus
      loading={false}
      data={{ items: [] }}
      error=""
      activeFilters
      load={vi.fn()}
      updateRoute={updateRoute}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "清除筛选" }));
  expect(updateRoute).toHaveBeenCalledWith({
    q: "",
    storeSite: "",
    listing: "",
    qualityStatus: "",
    page: 1,
  });
});

test.each(["", "review_required"])(
  "人工修正保存保留筛选 %s 和当前分页，并显示新状态",
  async (quality) => {
    const notify = vi.fn();
    apiMock.resultTaxonomy.mockResolvedValue({
      labels: [
        { code: "FIT_TOO_SMALL", name: "尺寸", allowed_sentiments: ["NEGATIVE"] },
      ],
    });
    apiMock.correctClassificationResult.mockResolvedValue({
      version_id: "classification-version-2",
    });
    apiMock.classificationResultVersions.mockImplementation((id) =>
      Promise.resolve([
        { ...resultVersion, version_id: id, version: id.endsWith("2") ? 2 : 1 },
      ]),
    );
    apiMock.classificationResult.mockImplementation((id) =>
      Promise.resolve({
        ...resultVersion,
        version_id: id,
        version: id.endsWith("2") ? 2 : 1,
      }),
    );
    const correctedRecord = {
      ...record,
      classification: {
        ...record.classification,
        human_review_assessment: {
          resolved: true,
          assessed_by_name: "测试人员",
          assessed_at: "2026-10-11T10:00:00Z",
        },
      },
    };
    apiMock.classificationResultRecordGroups.mockImplementation((id) =>
      Promise.resolve({
        items:
          id.endsWith("2") && quality
            ? []
            : [groupOf(id.endsWith("2") ? correctedRecord : record)],
        total: id.endsWith("2") && quality ? 20 : 40,
        source_total: 40,
      }),
    );
    window.location.hash = `classification-results?result_version_id=classification-version-1&record_page=2&record_quality_status=${quality}`;
    render(<ResultCreationHarness notify={notify} />);
    await userEvent.click(await screen.findByRole("button", { name: "查看证据" }));
    await userEvent.click(screen.getByRole("button", { name: "人工修正" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "保存修正" })).toBeEnabled(),
    );
    fireEvent.change(screen.getByLabelText("观点 1 用户观点"), {
      target: { value: "整体尺寸偏小" },
    });
    await userEvent.click(screen.getByRole("button", { name: "保存修正" }));
    await waitFor(() =>
      expect(window.location.hash).toContain("classification-version-2"),
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    if (quality) {
      await waitFor(() => expect(window.location.hash).not.toContain("record_page=2"));
      expect(window.location.hash).toContain("record_quality_status=review_required");
      expect(notify).toHaveBeenCalledWith(expect.stringContaining("移出当前筛选"));
      expect(apiMock.classificationResultRecordGroups).toHaveBeenLastCalledWith(
        "classification-version-2",
        expect.objectContaining({ page: 1, quality_status: quality }),
        expect.any(Object),
      );
    } else {
      expect(window.location.hash).toContain("record_page=2");
      expect(await screen.findByText("人工已修正")).toBeVisible();
      expect(notify).toHaveBeenCalledWith("人工修正已保存，无需重跑");
      await userEvent.click(screen.getByRole("button", { name: "查看证据" }));
      expect(screen.getByText("测试人员", { exact: false })).toBeVisible();
    }
  },
);

test("证据查看期间保留旧结果，关闭后备齐新数据整体切换并保留筛选页码", async () => {
  const nextVersion = {
    ...resultVersion,
    version_id: "classification-version-2",
    version: 2,
  };
  apiMock.classificationResultRecordGroups.mockResolvedValue({
    items: [groupOf(record)],
    total: 40,
    source_total: 40,
  });
  window.location.hash =
    "classification-results?result_version_id=classification-version-1&record_page=2&record_quality_status=ready";
  const view = render(<ResultCreationHarness />);
  await userEvent.click(await screen.findByRole("button", { name: "查看证据" }));
  await waitFor(() => expect(apiMock.classificationResultVersions).toHaveBeenCalled());
  apiMock.classificationResultVersions.mockResolvedValue([nextVersion, resultVersion]);
  let resolveOverview;
  apiMock.classificationResult.mockImplementation((id) =>
    id === nextVersion.version_id
      ? new Promise((resolve) => {
          resolveOverview = resolve;
        })
      : Promise.resolve(resultVersion),
  );
  vi.useFakeTimers();
  try {
    act(() => fireEvent(window, new Event("focus")));
    await act(async () => vi.advanceTimersByTimeAsync(100));
    expect(window.location.hash).toContain("classification-version-1");
    expect(screen.getByRole("dialog")).toBeVisible();
    expect(resolveOverview).toBeUndefined();
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "关闭证据抽屉" })),
    );
    expect(resolveOverview).toBeTypeOf("function");
    expect(window.location.hash).toContain("classification-version-1");
    expect(view.container.querySelector(".page-loading-state")).toBeNull();
    await act(async () => resolveOverview(nextVersion));
    await act(async () => vi.advanceTimersByTimeAsync(1));
    expect(window.location.hash).toContain("classification-version-2");
    expect(window.location.hash).toContain("record_page=2");
    expect(window.location.hash).toContain("record_quality_status=ready");
    expect(view.container.querySelector(".page-loading-state")).toBeNull();
  } finally {
    view.unmount();
    vi.useRealTimers();
  }
});

test("人工修改历史显示来源、变更数量和修正前后语义", async () => {
  const manual = {
    ...resultVersion,
    version_id: "manual-v2",
    version: 2,
    version_reason: "反馈组人工修正",
    parent_version_no: 1,
    parent_version_id: resultVersion.version_id,
    changed_unit_count: 1,
    inherited_unit_count: 2,
    created_by_name: "测试修正人",
    manual_change: {
      before: record,
      after: {
        ...record,
        classification: {
          ...record.classification,
          semantic_units: [
            {
              ...record.classification.semantic_units[0],
              opinion: "人工修正的尺寸问题",
            },
          ],
        },
      },
      reason: "人工修正语义",
    },
  };
  apiMock.classificationResultVersions.mockResolvedValue([manual, resultVersion]);
  render(<ResultVersionReviewPanel result={manual} onSelectVersion={vi.fn()} />);
  expect(await screen.findByText("v2 · 人工修正")).toBeVisible();
  expect(screen.getByText("测试修正人", { exact: false })).toBeVisible();
  expect(
    screen.getByText("基于 v1 修改 1 个分类单元，其余 2 个沿用来源版本"),
  ).toBeVisible();
  await userEvent.click(screen.getByText("查看人工修正前后", { selector: "summary" }));
  expect(
    within(screen.getByRole("region", { name: "修正前语义" })).getAllByText("尺码偏小")
      .length,
  ).toBeGreaterThan(0);
  expect(
    within(screen.getByRole("region", { name: "修正后语义" })).getAllByText(
      "人工修正的尺寸问题",
    ).length,
  ).toBeGreaterThan(0);
});
