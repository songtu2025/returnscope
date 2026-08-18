import { afterEach, beforeEach, expect, test, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { apiMock, dashboardApiMock } = vi.hoisted(() => ({
  apiMock: {
    classificationResults: vi.fn(),
    classificationResult: vi.fn(),
    classificationResultSummary: vi.fn(),
    classificationResultRecords: vi.fn(),
    classificationResultDrilldown: vi.fn(),
    classificationResultDownloadUrl: vi.fn(),
    classificationResultVersions: vi.fn(),
    reviewBatches: vi.fn(),
    createReviewBatch: vi.fn(),
    configs: vi.fn(),
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
  agent_family: "鞋履智能体",
  product_version: 4,
  published_at: "2026-08-12T08:00:00Z",
};

const record = {
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

beforeEach(() => {
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
  apiMock.classificationResultRecords.mockResolvedValue({
    items: [record],
    total: 1,
    page: 1,
    page_size: 20,
  });
  apiMock.classificationResultDrilldown.mockImplementation((_versionId, groupBy) => {
    const values = {
      problem: [
        {
          value: "FIT_TOO_SMALL",
          label_name: "偏小",
          record_count: 3,
          unit_count: 1,
        },
      ],
      product_name: [{ value: "产品表权威名称", record_count: 3, unit_count: 1 }],
      product_sku: [{ value: "PRODUCT-SKU-1", record_count: 3, unit_count: 1 }],
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

test("分类结果工作区整合结果版本、待复核和复核记录", async () => {
  const user = userEvent.setup();
  render(
    <ClassificationResultsPage
      route={{ query: {} }}
      notify={vi.fn()}
      userId="user-1"
    />,
  );

  expect(screen.getByRole("button", { name: "结果版本" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await user.click(screen.getByRole("button", { name: "待复核" }));
  expect(window.location.hash).toBe(
    "#classification-results?quality_status=review_required",
  );
  await user.click(screen.getByRole("button", { name: "复核记录" }));
  expect(window.location.hash).toBe("#classification-results?view=reviews");
});

afterEach(() => cleanup());

test("结果池使用服务端筛选并展示多产品名称", async () => {
  const user = userEvent.setup();
  window.location.hash =
    "classification-results?record_page=4&problem=STALE&product_name=STALE";
  render(<ClassificationResultsPage notify={vi.fn()} />);

  expect(await screen.findByText("产品表权威名称")).toBeVisible();
  expect(screen.getByText("另有 1 个产品名称")).toBeVisible();

  await user.type(screen.getByRole("textbox", { name: "搜索分类结果" }), "水鞋");
  await user.click(screen.getByRole("button", { name: "筛选" }));

  await waitFor(() =>
    expect(apiMock.classificationResults).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: "水鞋", page: 1, page_size: 20 }),
      expect.any(Object),
    ),
  );
  expect(window.location.hash).toContain("q=%E6%B0%B4%E9%9E%8B");

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
  apiMock.classificationResults.mockResolvedValue({
    items: [derived, needsReview],
    total: 2,
    page: 1,
    page_size: 20,
  });
  render(<ClassificationResultsPage notify={vi.fn()} userId="user-1" />);

  await userEvent.click(await screen.findByRole("button", { name: "新建分析看板" }));
  expect(screen.getByRole("checkbox", { name: "选择 DERIVED 结果 v2" })).toBeEnabled();
  expect(screen.getByRole("checkbox", { name: "选择 REVIEW 结果 v1" })).toBeEnabled();
  expect(screen.getByText(/自动排除待复核和已排除记录/)).toBeVisible();
});

test("从分类结果快速确认并创建 AI 洞察报告任务", async () => {
  const user = userEvent.setup();
  const notify = vi.fn();
  sessionStorage.clear();
  render(
    <ClassificationResultsPage route={{ query: {} }} notify={notify} userId="user-1" />,
  );

  await user.click(await screen.findByRole("checkbox", { name: "选择 SR001 结果 v1" }));
  expect(screen.getByText("已选 1 项")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "生成 AI 洞察" }));

  const dialog = await screen.findByRole("dialog", {
    name: "生成 AI 洞察报告",
  });
  expect(within(dialog).getByLabelText("模型")).toHaveDisplayValue(
    "GPT-5.6 · OpenAI 主接入",
  );
  expect(within(dialog).getByText(/待复核 1 条、已排除 1 条/)).toBeVisible();
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
  apiMock.classificationResultRecords.mockImplementation((_versionId, filters) => {
    const selected = filters.product_name === "产品表第二名称" ? secondRecord : record;
    return Promise.resolve({
      items: [selected],
      total: 1,
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
    expect(apiMock.classificationResultRecords).toHaveBeenCalledWith(
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
    expect(apiMock.classificationResultRecords).toHaveBeenLastCalledWith(
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
  expect(closeButton).toHaveFocus();
  await user.tab();
  expect(closeButton).toHaveFocus();
  await user.tab({ shift: true });
  expect(closeButton).toHaveFocus();
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
  apiMock.classificationResultRecords.mockResolvedValue({
    items: [],
    total: 0,
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

  expect(await screen.findByText("需复核")).toBeVisible();
  expect(screen.getByRole("button", { name: "创建复核批次" })).toBeEnabled();
  expect(
    screen.queryByRole("button", { name: "基于此版本创建看板" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByText(
      "尚未形成问题标签；当前 318 条均需复核，完成复核并发布派生版本后可按问题下钻。",
    ),
  ).toBeVisible();
  const problemColumn = screen.getByText("问题").closest(".drilldown-column");
  expect(within(problemColumn).getByText("尚未形成问题标签")).toBeVisible();
  expect(
    within(problemColumn).getByText(
      "当前 318 条记录需复核，完成复核并发布派生版本后，可按问题继续下钻。",
    ),
  ).toBeVisible();
  expect(within(problemColumn).queryByText("暂无数据")).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "创建复核批次" }));
  expect(
    await screen.findByRole("heading", {
      name: "基于分类结果 v1 创建批次",
    }),
  ).toBeVisible();
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
  apiMock.classificationResultRecords.mockResolvedValue({
    items: [],
    total: 0,
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

  expect(await screen.findByText("可用")).toBeVisible();
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

  expect(await screen.findByText("复核已发布")).toBeVisible();
  expect(screen.getByRole("button", { name: "查看衍生版本" })).toBeEnabled();
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

test("旧筛选轮询晚返回不会覆盖当前列表或触发新结果提示", async () => {
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
      vi.advanceTimersByTime(15000);
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
  expect(screen.getByText("v2 · 复核派生")).toBeVisible();
  expect(screen.getByText("人工复核后发布")).toBeVisible();
  expect(screen.getByText("发布人信息未提供", { exact: false })).toBeVisible();
  expect(screen.getByText("复核员乙", { exact: false })).toBeVisible();
  expect(
    screen.getByText("基于 v1 修改 2 个分类单元，其余 1 个沿用来源版本"),
  ).toBeVisible();
  expect(screen.getByText("复核批次：review-batch-1")).toBeInTheDocument();
  expect(apiMock.classificationResultRecords).not.toHaveBeenCalled();
  expect(apiMock.classificationResultDrilldown).not.toHaveBeenCalled();

  await userEvent.click(screen.getByRole("button", { name: "查看最新版本 v2" }));
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

  expect(await screen.findByText("v2 · 复核派生")).toBeVisible();
  expect(screen.queryByText(/修改 .* 个分类单元/)).not.toBeInTheDocument();
  expect(screen.getAllByText(/3 条记录 · 1 个分类单元/)).toHaveLength(2);
});

test("已有复核草稿只允许进入批次，不重复创建", async () => {
  const needsReview = { ...resultVersion, quality_status: "review_required" };
  apiMock.classificationResult.mockResolvedValue(needsReview);
  apiMock.classificationResultVersions.mockResolvedValue([needsReview]);
  apiMock.reviewBatches.mockResolvedValue({
    items: [
      {
        id: "review-batch-1",
        status: "draft",
        base_result_version_id: resultVersion.version_id,
      },
    ],
    total: 1,
    page: 1,
    page_size: 100,
  });
  window.location.hash =
    "classification-results?result_version_id=classification-version-1&tab=history";

  render(<ClassificationResultsPage notify={vi.fn()} />);
  await userEvent.click(await screen.findByRole("button", { name: /进入复核批次/ }));

  expect(apiMock.createReviewBatch).not.toHaveBeenCalled();
  expect(window.location.hash).toContain("review_batch_id=review-batch-1");
  expect(window.location.hash).toContain("result_version_id=classification-version-1");
});

test("创建复核批次要求原因并准确说明处理范围", async () => {
  const notify = vi.fn();
  const needsReview = { ...resultVersion, quality_status: "review_required" };
  apiMock.classificationResult.mockResolvedValue(needsReview);
  apiMock.classificationResultVersions.mockResolvedValue([needsReview]);
  apiMock.createReviewBatch.mockResolvedValue({
    id: "review-batch-created",
    base_result_version_id: needsReview.version_id,
    status: "draft",
  });
  window.location.hash =
    "classification-results?result_version_id=classification-version-1&tab=history&page=2&q=SR001&problem=FIT_TOO_SMALL";

  render(<ClassificationResultsPage notify={notify} />);
  await userEvent.click(await screen.findByRole("button", { name: "创建复核批次" }));
  expect(screen.getByText(/批次只加入当前版本中“需复核”的分类单元/)).toBeVisible();
  const submit = screen.getByRole("button", { name: "创建并进入批次" });
  expect(submit).toBeDisabled();
  await userEvent.type(
    screen.getByPlaceholderText("必填：说明为什么需要发起本次复核"),
    "检查低置信度分类",
  );
  await userEvent.click(submit);

  await waitFor(() =>
    expect(apiMock.createReviewBatch).toHaveBeenCalledWith("classification-version-1", {
      reason: "检查低置信度分类",
    }),
  );
  expect(window.location.hash).toContain("review_batch_id=review-batch-created");
  const reviewQuery = new URLSearchParams(window.location.hash.split("?")[1]);
  expect(reviewQuery.get("return_to")).toContain("page=2");
  expect(reviewQuery.get("return_to")).toContain("q=SR001");
  expect(reviewQuery.get("return_to")).toContain("problem=FIT_TOO_SMALL");
});

test("并发创建返回 409 时读取并进入服务器已有草稿", async () => {
  const needsReview = { ...resultVersion, quality_status: "review_required" };
  const conflict = Object.assign(new Error("该版本已有复核批次"), {
    status: 409,
  });
  apiMock.classificationResult.mockResolvedValue(needsReview);
  apiMock.classificationResultVersions.mockResolvedValue([needsReview]);
  apiMock.reviewBatches
    .mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 100 })
    .mockResolvedValue({
      items: [
        {
          id: "server-review-batch",
          status: "draft",
          base_result_version_id: needsReview.version_id,
        },
      ],
      total: 1,
      page: 1,
      page_size: 100,
    });
  apiMock.createReviewBatch.mockRejectedValue(conflict);
  window.location.hash =
    "classification-results?result_version_id=classification-version-1&tab=history";

  render(<ClassificationResultsPage notify={vi.fn()} />);
  await userEvent.click(await screen.findByRole("button", { name: "创建复核批次" }));
  await userEvent.type(
    screen.getByPlaceholderText("必填：说明为什么需要发起本次复核"),
    "并发复核",
  );
  await userEvent.click(screen.getByRole("button", { name: "创建并进入批次" }));

  await waitFor(() =>
    expect(window.location.hash).toContain("review_batch_id=server-review-batch"),
  );
  expect(apiMock.reviewBatches).toHaveBeenLastCalledWith({
    page: 1,
    page_size: 100,
    base_result_version_id: "classification-version-1",
  });
});
