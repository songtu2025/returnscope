import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    me: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    status: vi.fn(),
    tasks: vi.fn(),
    task: vi.fn(),
    preflightTask: vi.fn(),
    preflightTaskReplan: vi.fn(),
    replanTask: vi.fn(),
    resumeTask: vi.fn(),
    retryTaskSegment: vi.fn(),
    retrySegmentResultPublish: vi.fn(),
    reorderTaskSegments: vi.fn(),
    controlTaskSegment: vi.fn(),
    setTaskParallelism: vi.fn(),
    analysis: vi.fn(),
    analysisDownloadUrl: vi.fn(),
    taskEvents: vi.fn(),
    eventUrl: vi.fn(),
    downloadUrl: vi.fn(),
    segmentDownloadUrl: vi.fn(),
    classificationResultDownloadUrl: vi.fn(),
    classificationResults: vi.fn(),
    datasets: vi.fn(),
    dataset: vi.fn(),
    datasetRows: vi.fn(),
    datasetDownloadUrl: vi.fn(),
    completeProductCategories: vi.fn(),
    dataVersions: vi.fn(),
    qualityPreflight: vi.fn(),
    productScopes: vi.fn(),
    createDataset: vi.fn(),
    addDatasetVersion: vi.fn(),
    configs: vi.fn(),
    activeValidation: vi.fn(),
    startModelValidation: vi.fn(),
    validationEventUrl: vi.fn(),
    validationRun: vi.fn(),
    reviews: vi.fn(),
    review: vi.fn(),
    taxonomy: vi.fn(),
    resolveReview: vi.fn(),
    createTask: vi.fn(),
    createConfig: vi.fn(),
    discardConfig: vi.fn(),
    createModel: vi.fn(),
    discoverModels: vi.fn(),
    updateModel: vi.fn(),
    publishConfig: vi.fn(),
    startConfigValidation: vi.fn(),
    modelPreference: vi.fn(),
    saveModelPreference: vi.fn(),
    users: vi.fn(),
  },
}));

vi.mock("../src/api", () => ({
  api: apiMock,
  ApiError: class ApiError extends Error {},
}));
vi.mock("../src/shared/api/taskApi", () => ({
  taskApi: { tasks: apiMock.tasks },
}));
vi.mock("../src/shared/api/resultApi", () => ({
  resultApi: { classificationResults: apiMock.classificationResults },
}));

import { App, Sidebar } from "../src/App";
import { ApiManagement } from "../src/pages/ApiManagement";
import { ModelPreferencePage } from "../src/features/system-settings/ModelPreferencePage";
import { SystemSettingsPage } from "../src/features/system-settings/SystemSettingsPage";
import { DataManagement } from "../src/pages/DataManagement";
import { ReviewCenter } from "../src/pages/ReviewCenter";
import { ResultsPage } from "../src/pages/ResultsPage";
import { TeamPage } from "../src/pages/TeamPage";
import { NewTaskPage, TaskMonitor } from "../src/pages/Tasks";
import { SESSION_EXPIRED_EVENT } from "../src/shared/api/request";

const systemStatus = {
  worker_status: "ok",
  my_running_tasks: 0,
  pending_reviews: 1,
  task_counts: {},
  warnings: [],
};

test("分类结果角标只使用新版批次待处理数", () => {
  const { rerender } = render(
    <Sidebar
      page="workbench"
      system={{ pending_reviews: 9, pending_review_batches: 0 }}
      onNavigate={vi.fn()}
    />,
  );
  const resultNavigation = screen.getByRole("button", { name: "分类结果" });
  expect(within(resultNavigation).queryByText("9")).not.toBeInTheDocument();

  rerender(
    <Sidebar
      page="workbench"
      system={{ pending_reviews: 9, pending_review_batches: 2 }}
      onNavigate={vi.fn()}
    />,
  );
  expect(
    within(screen.getByRole("button", { name: /分类结果/ })).getByText("2"),
  ).toBeVisible();
});

const executionPlan = {
  registry_version: "category-capabilities-v1",
  plan_hash: "a".repeat(64),
  scope_mode: "auto",
  primary_store: "SEEKWAY:US",
  detected_scopes: [
    {
      store: "SEEKWAY:US",
      listing: "SK001",
      record_count: 12,
      unique_comments: 8,
    },
  ],
  unresolved_scope_count: 0,
  unresolved_scope_record_count: 0,
  record_count: 12,
  valid_comment_count: 10,
  unique_comment_count: 8,
  executable_count: 8,
  executable_record_count: 12,
  blocked_count: 0,
  blocked_record_count: 0,
  missing_category_count: 0,
  missing_category_record_count: 0,
  missing_categories: [],
  unknown_category_count: 0,
  unknown_category_record_count: 0,
  unknown_categories: [],
  segments: [
    {
      segment_key: "footwear",
      agent_key: "footwear",
      agent_family: "鞋履智能体",
      scope: { store: "SEEKWAY:US", listing: "SK001" },
      logic_version: "footwear-v2",
      taxonomy_version: "taxonomy-v3",
      record_count: 12,
      unique_comments: 8,
      status: "ready",
      variants: [
        {
          category_a: "鞋履",
          category_b: "薄底水鞋",
          record_count: 12,
          unique_comments: 8,
        },
      ],
    },
  ],
};

beforeEach(() => {
  window.location.hash = "";
  Object.values(apiMock).forEach((mock) => mock.mockReset());
  apiMock.status.mockResolvedValue(systemStatus);
  apiMock.tasks.mockResolvedValue([]);
  apiMock.classificationResults.mockResolvedValue({ items: [], total: 0 });
  apiMock.datasets.mockResolvedValue([]);
  apiMock.datasetRows.mockResolvedValue({ records: [], total: 0 });
  apiMock.reviews.mockResolvedValue([]);
  apiMock.configs.mockResolvedValue([]);
  apiMock.modelPreference.mockResolvedValue(null);
  apiMock.dataVersions.mockResolvedValue([]);
  apiMock.qualityPreflight.mockResolvedValue({
    counts: {
      total_records: 12,
      matched_records: 12,
      unmatched_records: 0,
    },
  });
  apiMock.productScopes.mockResolvedValue([]);
  apiMock.taxonomy.mockResolvedValue({ labels: [] });
  apiMock.activeValidation.mockResolvedValue(null);
  apiMock.users.mockResolvedValue([]);
  apiMock.eventUrl.mockReturnValue("/events");
  apiMock.validationEventUrl.mockReturnValue("/validation-events");
  apiMock.analysisDownloadUrl.mockReturnValue("/analysis-download");
  apiMock.segmentDownloadUrl.mockReturnValue("/segment-download");
  apiMock.classificationResultDownloadUrl.mockReturnValue("/classification-download");
  apiMock.preflightTask.mockResolvedValue(executionPlan);
});

afterEach(() => cleanup());

describe("关键用户流程", () => {
  test("运行配置加载完成前不显示缺失准备提示", async () => {
    let resolveVersions;
    let resolveConfigs;
    apiMock.dataVersions.mockReturnValue(
      new Promise((resolve) => {
        resolveVersions = resolve;
      }),
    );
    apiMock.configs.mockReturnValue(
      new Promise((resolve) => {
        resolveConfigs = resolve;
      }),
    );

    render(<NewTaskPage notify={vi.fn()} onChanged={vi.fn()} onNavigate={vi.fn()} />);

    expect(screen.getByText("正在读取数据与模型配置…")).toBeVisible();
    expect(screen.queryByText("还需要完成运行准备")).not.toBeInTheDocument();

    resolveVersions([]);
    resolveConfigs([]);
    expect(await screen.findByText("还需要完成运行准备")).toBeVisible();
  });

  test("用户登录后进入任务工作台", async () => {
    const user = userEvent.setup();
    apiMock.me.mockRejectedValue(new Error("未登录"));
    apiMock.login.mockResolvedValue({
      id: "user-1",
      email: "admin@example.com",
      display_name: "管理员",
    });

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "登录并继续分析" }),
    ).toBeVisible();
    await user.type(screen.getByLabelText("邮箱"), "admin@example.com");
    await user.type(screen.getByLabelText("密码"), "secure-password");
    await user.click(screen.getByRole("button", { name: /进入工作台/ }));

    await waitFor(() =>
      expect(apiMock.login).toHaveBeenCalledWith(
        "admin@example.com",
        "secure-password",
      ),
    );
    expect(await screen.findByRole("navigation", { name: "主导航" })).toBeVisible();
  });

  test("任意子页面会话失效后退出已登录应用壳", async () => {
    apiMock.me.mockResolvedValue({
      id: "user-1",
      email: "admin@example.com",
      display_name: "管理员",
    });

    render(<App />);
    expect(await screen.findByRole("heading", { name: "首页" })).toBeVisible();

    act(() => window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT)));

    expect(
      await screen.findByRole("heading", { name: "登录并继续分析" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("navigation", { name: "主导航" }),
    ).not.toBeInTheDocument();
  });

  test("浏览器前进后退可以恢复对应页面", async () => {
    apiMock.me.mockResolvedValue({
      id: "user-1",
      email: "admin@example.com",
      display_name: "管理员",
    });

    render(<App />);
    expect(await screen.findByRole("heading", { name: "首页" })).toBeVisible();

    window.location.hash = "data";
    window.dispatchEvent(new HashChangeEvent("hashchange"));

    expect(await screen.findByRole("heading", { name: "产品信息" })).toBeVisible();
  });

  test("旧复核地址只进入历史单记录复核并明确与新版隔离", async () => {
    apiMock.me.mockResolvedValue({
      id: "user-1",
      email: "admin@example.com",
      display_name: "管理员",
    });
    window.location.hash = "review";

    render(<App />);

    expect(await screen.findByText("旧版单记录复核")).toBeVisible();
    expect(
      screen.getByText("仅用于历史任务，与新版复核批次和派生版本相互独立。"),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "进入分类结果复核记录" })).toBeVisible();
  });

  test("分析结果可以在五个分析层级间切换", async () => {
    const user = userEvent.setup();
    apiMock.tasks.mockResolvedValue([
      {
        id: "task-1",
        title: "SK001 分析",
        status: "completed",
        store: "SEEKWAY:US",
        listing: "SK001",
        result_version: 2,
        dataset_name: "退货数据",
        dataset_version: 1,
        completed_at: "2026-08-10T09:00:00Z",
      },
      {
        id: "task-partial-result",
        title: "历史中止任务",
        status: "cancelled",
        result_file_path: "runtime/results/task/analysis-partial-v1.xlsx",
        store: "SEEKWAY:US",
        listing: "SK002",
        result_version: 1,
        dataset_name: "退货数据",
        dataset_version: 1,
        completed_at: "2026-08-10T10:00:00Z",
      },
    ]);
    apiMock.task.mockResolvedValue({
      id: "task-live-result",
      title: "批量任务",
      status: "running",
      store: "SEEKWAY:US",
      result_version: 0,
      dataset_name: "退货数据",
      dataset_version: 1,
      segments: [
        {
          id: "segment-sr001",
          status: "completed",
          result_file_path: "runtime/results/sr001.xlsx",
          scope: { store: "SEEKWAY:US", listing: "SR001" },
        },
      ],
    });
    const analysisPayload = {
      scope: { total_records: 12, filtered_records: 12 },
      filters: {
        date_min: "2026-08-01",
        date_max: "2026-08-10",
        category_as: ["水鞋"],
        category_bs: ["薄底水鞋"],
        listings: ["SK001"],
        skus: ["SKU-1"],
        asins: ["ASIN-1"],
        reasons: ["APPAREL_TOO_LARGE"],
        statuses: ["AUTO_APPROVED"],
        claim_relations: [],
        problem_labels: [{ code: "SIZE_LARGE", name: "偏大", group: "尺码" }],
      },
      overview: {
        metrics: {
          total_records: 12,
          listing_count: 1,
          sku_count: 2,
          text_records: 10,
          text_coverage: 0.833,
          review_records: 2,
          review_rate: 0.2,
          product_matched: 12,
          product_match_rate: 1,
        },
        trend: [],
        top_problems: [],
        listing_problems: [],
        listing_quality: [],
        parts: [],
      },
      diagnosis: {
        focus_code: "SIZE_LARGE",
        priorities: [
          {
            code: "SIZE_LARGE",
            name: "偏大",
            group: "尺码",
            records: 6,
            share: 0.5,
            change_pp: 1.2,
            sku_count: 2,
            top_sku_share: 0.6,
            multi_problem_records: 1,
            review_records: 1,
          },
        ],
        product_locations: [],
        reasons: [],
        parts: [],
        pairs: [],
        comments: [],
      },
      products: { dimension: "listing", summary: [], matrix: [] },
      quality: {
        metrics: { review_comments: 2, conflicts: 1, unknown_records: 0 },
        listing_quality: [],
        statuses: [],
        review_reasons: [],
        unknowns: [],
      },
      details: {
        total: 1,
        page: 1,
        pages: 1,
        records: [
          {
            order_id: "ORDER-1",
            return_date: "2026-08-01",
            sku: "SKU-1",
            asin: "ASIN-1",
            listing: "SK001",
            category_b: "薄底水鞋",
            reason: "APPAREL_TOO_LARGE",
            primary_labels: "SIZE_LARGE:偏大",
            status: "AUTO_APPROVED",
            comment: "鞋子太大",
          },
        ],
      },
    };
    apiMock.analysis.mockImplementation((_id, query) =>
      Promise.resolve({ ...analysisPayload, view: query.view }),
    );

    render(
      <ResultsPage
        notify={vi.fn()}
        onNavigate={vi.fn()}
        focus={{ kind: "result", id: "task-live-result", listing: "SR001" }}
      />,
    );

    await waitFor(() =>
      expect(apiMock.analysis).toHaveBeenCalledWith(
        "task-live-result",
        expect.objectContaining({ listing: "SR001", view: "overview" }),
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      ),
    );
    expect(
      screen.getByRole("option", { name: "历史中止任务（部分结果）" }),
    ).toBeVisible();
    expect(screen.getByText("退货记录").parentElement).toHaveTextContent("12");
    await user.click(screen.getByRole("tab", { name: "问题诊断" }));
    expect(await screen.findByRole("heading", { name: "问题优先级" })).toBeVisible();
    expect(apiMock.analysis).toHaveBeenLastCalledWith(
      "task-live-result",
      expect.objectContaining({ listing: "SR001", view: "diagnosis" }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    await user.click(screen.getByRole("tab", { name: "数据明细" }));
    expect(await screen.findByText("鞋子太大")).toBeVisible();
    expect(apiMock.analysis).toHaveBeenLastCalledWith(
      "task-live-result",
      expect.objectContaining({ listing: "SR001", view: "details" }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  test("零标签覆盖时明确提示结果不可用于分析", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    apiMock.tasks.mockResolvedValue([
      {
        id: "task-empty-labels",
        title: "SR001 分析",
        status: "completed",
        store: "SEEKWAY:US",
        listing: "SR001",
        result_version: 1,
        dataset_name: "退货数据",
        dataset_version: 1,
        completed_at: "2026-08-12T09:00:00Z",
      },
    ]);
    apiMock.analysis.mockImplementation((_id, query) =>
      Promise.resolve({
        view: query.view,
        scope: { total_records: 318, filtered_records: 318 },
        filters: {
          date_min: "2026-08-01",
          date_max: "2026-08-12",
          category_as: ["鞋履"],
          category_bs: ["休闲运动水鞋"],
          listings: ["SR001"],
          skus: [],
          asins: [],
          reasons: [],
          statuses: ["MANUAL_REVIEW"],
          claim_relations: [],
          problem_labels: [],
        },
        overview: {
          metrics: {
            total_records: 318,
            listing_count: 1,
            sku_count: 76,
            text_records: 318,
            text_coverage: 1,
            review_records: 318,
            review_rate: 1,
            product_matched: 318,
            product_match_rate: 1,
          },
          top_problems: [],
          listing_problems: [],
          listing_quality: [],
          parts: [],
        },
        quality_gate: {
          status: "unusable",
          text_records: 318,
          labeled_records: 0,
          label_coverage: 0,
          review_records: 318,
          review_rate: 1,
          review_reasons: [{ name: "证据不在原评论中", records: 224 }],
        },
        quality: {
          metrics: { review_comments: 224, conflicts: 0, unknown_records: 0 },
          listing_quality: [],
          statuses: [],
          review_reasons: [{ name: "证据不在原评论中", records: 224 }],
          unknowns: [],
        },
      }),
    );

    render(<ResultsPage notify={vi.fn()} onNavigate={onNavigate} />);

    expect(await screen.findByText("本批结果尚不能用于问题分析")).toBeVisible();
    expect(screen.getByText(/当前没有可聚合的问题标签/)).toBeVisible();
    expect(screen.getByText(/当前结果的标签覆盖率为 0%/)).toBeVisible();

    await user.click(screen.getByRole("button", { name: "查看复核原因" }));
    await waitFor(() =>
      expect(apiMock.analysis).toHaveBeenLastCalledWith(
        "task-empty-labels",
        expect.objectContaining({ view: "quality" }),
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      ),
    );

    await user.click(screen.getByRole("button", { name: "检查模型配置" }));
    expect(onNavigate).toHaveBeenCalledWith("api");
  });

  test("用户可以选择快照并创建分析任务", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    const onChanged = vi.fn();
    apiMock.dataVersions.mockResolvedValue([
      {
        kind: "returns",
        version_id: "returns-v1",
        dataset_name: "8月退货数据",
        version: 1,
        current_version: 1,
        row_count: 12,
      },
      {
        kind: "products",
        dataset_id: "products-dataset",
        version_id: "products-v2",
        dataset_name: "商品维度",
        version: 2,
        current_version: 2,
        row_count: 6,
      },
    ]);
    apiMock.configs.mockResolvedValue([
      {
        id: "conn-1",
        name: "生产线路",
        active_version: {
          id: "cfg-1",
          version: 1,
          cheap_audit_percent: 5,
          primary_model: "gpt-main",
          primary_effort: "medium",
        },
      },
    ]);
    apiMock.productScopes.mockResolvedValue([
      { store: "SEEKWAY:US", listings: ["SK001"] },
    ]);
    apiMock.preflightTask.mockResolvedValue({
      ...executionPlan,
      unique_comment_count: 10,
      excluded_count: 2,
      excluded_record_count: 3,
      missing_category_count: 2,
      missing_category_record_count: 3,
      missing_categories: [
        {
          category_a: "",
          category_b: "",
          record_count: 3,
          unique_comments: 2,
        },
      ],
      segments: [
        executionPlan.segments[0],
        {
          ...executionPlan.segments[0],
          segment_key: "eyewear",
          agent_key: "eyewear",
          agent_family: "眼镜智能体",
          scope: { store: "SEEKWAY:US", listing: "SK002" },
        },
      ],
    });
    apiMock.qualityPreflight.mockResolvedValue({
      counts: {
        total_records: 12,
        matched_records: 9,
        unmatched_records: 3,
      },
    });
    apiMock.createTask.mockResolvedValue({ id: "task-1" });

    render(
      <NewTaskPage notify={vi.fn()} onChanged={onChanged} onNavigate={onNavigate} />,
    );

    expect(await screen.findByText("待分析数据")).toBeVisible();
    expect(screen.queryByLabelText("商品维度版本")).not.toBeInTheDocument();
    const planButton = screen.getByRole("button", { name: /生成执行计划/ });
    expect(planButton).toBe(planButton.closest(".task-create-summary").children[1]);
    await user.type(screen.getByLabelText("任务名称（可选）"), "US站退货分析");
    await user.clear(screen.getByLabelText(/^本次初筛抽检比例/));
    await user.type(screen.getByLabelText(/^本次初筛抽检比例/), "12");
    await user.click(planButton);
    expect(await screen.findByText("部分可执行")).toBeVisible();
    expect(apiMock.preflightTask).toHaveBeenCalledWith(
      expect.objectContaining({
        model_policy: expect.objectContaining({ cheap_audit_percent: 12 }),
      }),
    );
    expect(screen.getByText("2 组评论不进入语义分析")).toBeVisible();
    expect(screen.getByText("75.00%")).toBeVisible();
    expect(screen.getByText("去重评论已对账：10 = 8 + 2")).toBeVisible();
    expect(screen.queryByText("选择未解决品类处理方式")).not.toBeInTheDocument();
    for (const label of ["正在解析", "商品匹配", "品类路由", "生成计划"]) {
      expect(screen.getByText(label)).toBeVisible();
    }
    await user.click(screen.getByRole("button", { name: "置顶 SK002" }));
    const startButton = screen.getByRole("button", {
      name: /启动 8 组可执行评论/,
    });
    expect(startButton).toBeDisabled();
    await user.click(screen.getByLabelText(/我确认本次仅分析 8 组评论/));
    await user.click(startButton);

    await waitFor(() =>
      expect(apiMock.createTask).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "US站退货分析",
          dataset_version_id: "returns-v1",
          product_version_id: "products-v2",
          config_version_id: "cfg-1",
          store: null,
          listing: null,
          plan_hash: "a".repeat(64),
          unresolved_policy: "block_all",
          segment_order: ["eyewear", "footwear"],
          model_policy: expect.objectContaining({ cheap_audit_percent: 12 }),
        }),
      ),
    );
    expect(onChanged).toHaveBeenCalled();
    expect(onNavigate).toHaveBeenCalledWith("tasks");
  });

  test("新建任务时可以追加并自动选中退货数据新版本", async () => {
    const user = userEvent.setup();
    const notify = vi.fn();
    const onChanged = vi.fn();
    const initialVersions = [
      {
        kind: "returns",
        dataset_id: "returns-old",
        version_id: "returns-v1",
        dataset_name: "原退货数据",
        version: 1,
        current_version: 1,
        row_count: 12,
      },
      {
        kind: "products",
        dataset_id: "products-dataset",
        version_id: "products-v1",
        dataset_name: "商品维度",
        version: 1,
        current_version: 1,
        row_count: 6,
      },
    ];
    const updatedVersions = [
      {
        kind: "returns",
        dataset_id: "returns-old",
        version_id: "returns-v2",
        dataset_name: "原退货数据",
        version: 2,
        current_version: 2,
        row_count: 20,
        quality: {
          matching_key_ready_rows: 20,
          missing_store_rows: 0,
          missing_sku_rows: 0,
        },
      },
      ...initialVersions,
    ];
    apiMock.dataVersions
      .mockResolvedValueOnce(initialVersions)
      .mockResolvedValueOnce(updatedVersions);
    apiMock.configs.mockResolvedValue([
      {
        id: "conn-1",
        name: "生产线路",
        active_version: {
          id: "cfg-1",
          version: 1,
          primary_model: "gpt-main",
          primary_effort: "medium",
        },
      },
    ]);
    apiMock.productScopes.mockResolvedValue([
      { store: "SEEKWAY:US", listings: ["SK001"] },
    ]);
    apiMock.addDatasetVersion.mockResolvedValue({ id: "returns-old" });

    const { container } = render(
      <NewTaskPage notify={notify} onChanged={onChanged} onNavigate={vi.fn()} />,
    );

    await user.click(await screen.findByRole("button", { name: "导入退货明细" }));
    await user.type(screen.getByLabelText("版本说明"), "删除无效数据后重新导入");
    await user.upload(
      container.querySelector('input[type="file"]'),
      new File(["comment"], "returns.csv"),
    );
    await user.click(screen.getByRole("button", { name: "创建不可变版本" }));

    await waitFor(() =>
      expect(screen.getByLabelText("退货明细")).toHaveValue("returns-v2"),
    );
    expect(apiMock.addDatasetVersion).toHaveBeenCalledOnce();
    const body = apiMock.addDatasetVersion.mock.calls[0][1];
    expect(body.get("default_store")).toBe("SEEKWAY:US");
    expect(body.get("change_note")).toBe("删除无效数据后重新导入");
    expect(onChanged).toHaveBeenCalledOnce();
    expect(notify).toHaveBeenCalledWith("新版本已上传并自动选中");
  });

  test("存在未知品类时必须选择策略并处理计划过期", async () => {
    const user = userEvent.setup();
    apiMock.dataVersions.mockResolvedValue([
      {
        kind: "returns",
        version_id: "returns-v1",
        dataset_name: "退货数据",
        version: 1,
        current_version: 1,
        row_count: 12,
      },
      {
        kind: "products",
        dataset_id: "products-dataset",
        version_id: "products-v1",
        dataset_name: "商品维度",
        version: 1,
        current_version: 1,
        row_count: 6,
      },
    ]);
    apiMock.configs.mockResolvedValue([
      {
        id: "conn-1",
        name: "生产线路",
        active_version: {
          id: "cfg-1",
          version: 1,
          primary_model: "gpt-main",
          primary_effort: "medium",
        },
      },
    ]);
    apiMock.productScopes.mockResolvedValue([{ store: "SEEKWAY:US", listings: [] }]);
    apiMock.preflightTask.mockResolvedValue({
      ...executionPlan,
      unique_comment_count: 10,
      excluded_count: 2,
      blocked_count: 2,
      blocked_record_count: 3,
      unknown_category_count: 2,
      unknown_category_record_count: 3,
      unknown_categories: [
        {
          category_a: "鞋履",
          category_b: "未知鞋型",
          record_count: 3,
          unique_comments: 2,
        },
      ],
      segments: [
        ...executionPlan.segments,
        {
          segment_key: "unknown",
          agent_key: "unknown",
          agent_family: "未配置品类",
          logic_version: null,
          taxonomy_version: "unresolved-category-v1",
          record_count: 3,
          unique_comments: 2,
          status: "blocked",
          variants: [
            {
              category_a: "鞋履",
              category_b: "未知鞋型",
              record_count: 3,
              unique_comments: 2,
            },
          ],
        },
      ],
    });
    apiMock.createTask.mockRejectedValue(
      Object.assign(new Error("执行计划已变化"), { status: 409 }),
    );

    render(<NewTaskPage notify={vi.fn()} onChanged={vi.fn()} onNavigate={vi.fn()} />);
    await screen.findByText("待分析数据");
    await user.click(screen.getByRole("button", { name: /生成执行计划/ }));
    expect(await screen.findByText("需要处理")).toBeVisible();
    expect(await screen.findByText("鞋履 / 未知鞋型 · 3 条")).toBeVisible();
    const startButton = screen.getByRole("button", {
      name: /选择处理方式后继续/,
    });
    expect(startButton).toBeDisabled();
    await user.click(screen.getByLabelText(/先运行已就绪/));
    const runReadyButton = screen.getByRole("button", {
      name: /启动 8 组已就绪评论/,
    });
    expect(runReadyButton).toBeDisabled();
    await user.click(screen.getByLabelText(/我确认本次仅分析 8 组评论/));
    await user.click(runReadyButton);

    await waitFor(() =>
      expect(apiMock.createTask).toHaveBeenCalledWith(
        expect.objectContaining({ unresolved_policy: "run_ready" }),
      ),
    );
    expect(
      await screen.findByText("执行计划已变化，请重新预检后再启动任务。"),
    ).toBeVisible();
  });

  test("阻断计划可以分组确认商品关联并用新维度重新预检", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    apiMock.dataVersions.mockResolvedValueOnce([
      {
        kind: "returns",
        version_id: "returns-v1",
        dataset_name: "退货数据",
        version: 1,
        current_version: 1,
        row_count: 12,
      },
      {
        kind: "products",
        dataset_id: "products-dataset",
        version_id: "products-v1",
        dataset_name: "商品维度",
        version: 1,
        current_version: 1,
        row_count: 6,
      },
    ]);
    apiMock.dataVersions.mockResolvedValueOnce([
      {
        kind: "returns",
        version_id: "returns-v1",
        dataset_name: "退货数据",
        version: 1,
        current_version: 1,
        row_count: 12,
      },
      {
        kind: "products",
        dataset_id: "products-dataset",
        version_id: "products-v2",
        dataset_name: "商品维度",
        version: 2,
        current_version: 2,
        row_count: 9,
      },
    ]);
    apiMock.configs.mockResolvedValue([
      {
        id: "conn-1",
        name: "生产线路",
        active_version: {
          id: "cfg-1",
          version: 1,
          primary_model: "gpt-main",
          primary_effort: "medium",
        },
      },
    ]);
    apiMock.productScopes.mockResolvedValue([{ store: "SEEKWAY:US", listings: [] }]);
    apiMock.preflightTask.mockResolvedValue({
      ...executionPlan,
      blocked_count: 12,
      missing_category_count: 12,
      missing_categories: [],
      unknown_category_count: 0,
      unknown_categories: [],
      category_options: [
        { category_a: "水鞋", category_b: "薄底水鞋" },
        { category_a: "水鞋", category_b: "厚底水鞋" },
        { category_a: "眼镜", category_b: "儿童眼镜" },
      ],
      unresolved_product_count: 3,
      unresolved_products: [
        {
          product_key: "SP001-406 Black New 41",
          store: "SEEKWAY:CA",
          msku: "SP001-406 Black New 41",
          suggested_listing: "SP001",
          record_count: 5,
          comment_count: 5,
          editable: true,
          match_status: "high_confidence",
          match_candidate: {
            msku: "SP001-406 Black 41",
            listing: "SP001",
            product_name: "SP001-406 黑",
            category_a: "水鞋",
            category_b: "厚底水鞋",
            match_score: 100,
          },
        },
        {
          product_key: "SK002-1431 Leaf&amp;Feather 40-41",
          store: "SEEKWAY:US",
          msku: "SK002-1431 Leaf&amp;Feather 40-41",
          suggested_listing: "SK002",
          record_count: 4,
          comment_count: 4,
          editable: true,
          match_status: "high_confidence",
          match_candidate: {
            msku: "SK002-1431 Leaf&Feather 40-41",
            listing: "SK002",
            product_name: "SK002-1431 叶子羽毛",
            category_a: "水鞋",
            category_b: "薄底水鞋",
            match_score: 100,
          },
        },
        {
          product_key: "SK002-1302 coconut tree 40-41(CA)",
          store: "SEEKWAY:US",
          msku: "SK002-1302 coconut tree 40-41(CA)",
          suggested_listing: "SK002",
          record_count: 3,
          comment_count: 3,
          editable: true,
          match_status: "needs_review",
        },
      ],
    });
    apiMock.completeProductCategories.mockResolvedValue({
      current_version: 2,
      versions: [{ id: "products-v2", version: 2 }],
    });

    render(
      <NewTaskPage notify={vi.fn()} onChanged={vi.fn()} onNavigate={onNavigate} />,
    );
    await screen.findByText("待分析数据");
    await user.click(screen.getByRole("button", { name: /生成执行计划/ }));
    await user.click(
      await screen.findByRole("button", { name: /处理 3 个商品匹配异常/ }),
    );
    expect(screen.getByRole("heading", { name: "处理商品匹配异常" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "高匹配建议（1）" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "需人工确认（1）" })).toBeVisible();
    expect(
      screen.getByLabelText("SEEKWAY:US SK002-1302 coconut tree 40-41(CA) Listing"),
    ).toHaveValue("SK002");
    await user.selectOptions(
      screen.getByLabelText("SEEKWAY:US SK002-1302 coconut tree 40-41(CA) 品类A"),
      "水鞋",
    );
    await user.selectOptions(
      screen.getByLabelText("SEEKWAY:US SK002-1302 coconut tree 40-41(CA) 品类B"),
      "薄底水鞋",
    );
    await user.click(screen.getByLabelText("选择全部 Listing 组"));
    await user.click(screen.getByRole("button", { name: "确认所选关联" }));
    await user.click(screen.getByRole("button", { name: "保存关联并重新生成计划" }));

    await waitFor(() =>
      expect(apiMock.completeProductCategories).toHaveBeenCalledWith(
        "products-dataset",
        expect.objectContaining({
          expected_version: 1,
          store: "SEEKWAY:US",
          items: expect.arrayContaining([
            expect.objectContaining({
              store: "SEEKWAY:CA",
              msku: "SP001-406 Black New 41",
              listing: "SP001",
              category_a: "水鞋",
              category_b: "厚底水鞋",
            }),
            expect.objectContaining({
              store: "SEEKWAY:US",
              msku: "SK002-1431 Leaf&amp;Feather 40-41",
              listing: "SK002",
              category_a: "水鞋",
              category_b: "薄底水鞋",
            }),
          ]),
        }),
      ),
    );
    expect(onNavigate).not.toHaveBeenCalled();
  });

  test("商品维度补充完成后可以返回任务并使用最新版本", async () => {
    const user = userEvent.setup();
    const onReturnToTask = vi.fn();
    const productDataset = {
      id: "products-dataset",
      kind: "products",
      name: "商品维度",
      description: "",
      current_version: 2,
      row_count: 6,
      column_count: 6,
      updated_at: "2026-08-11T08:00:00Z",
      quality: { complete_rate: 100 },
      schema: [],
      audit: [],
      versions: [{ id: "products-v2", version: 2 }],
    };
    apiMock.datasets.mockResolvedValue([productDataset]);
    apiMock.dataset.mockResolvedValue(productDataset);

    render(
      <DataManagement
        notify={vi.fn()}
        onNavigate={vi.fn()}
        focus={{
          kind: "dataset",
          id: "products-dataset",
          datasetKind: "products",
          returnToTask: true,
        }}
        taskDraft={{ form: { product_version_id: "products-v1" }, step: 3 }}
        onReturnToTask={onReturnToTask}
      />,
    );

    expect(await screen.findByRole("button", { name: "产品列表" })).toHaveClass(
      "active",
    );
    expect(screen.getByRole("heading", { name: "商品维度" })).toBeVisible();
    await user.click(await screen.findByRole("button", { name: /返回任务并重新预检/ }));
    expect(onReturnToTask).toHaveBeenCalledWith("products-v2");
  });

  test("任务跳转后只展示缺失商品并可批量补充后重新预检", async () => {
    const user = userEvent.setup();
    const onReturnToTask = vi.fn();
    const productDataset = {
      id: "products-dataset",
      kind: "products",
      name: "商品维度",
      description: "",
      current_version: 2,
      row_count: 6,
      column_count: 7,
      updated_at: "2026-08-11T08:00:00Z",
      quality: { complete_rate: 100 },
      schema: [],
      audit: [],
      versions: [{ id: "products-v2", version: 2 }],
    };
    apiMock.datasets.mockResolvedValue([productDataset]);
    apiMock.dataset.mockResolvedValue(productDataset);
    apiMock.completeProductCategories.mockResolvedValue({
      ...productDataset,
      current_version: 3,
      versions: [
        { id: "products-v3", version: 3 },
        { id: "products-v2", version: 2 },
      ],
    });

    render(
      <DataManagement
        notify={vi.fn()}
        onNavigate={vi.fn()}
        focus={{
          kind: "dataset",
          id: "products-dataset",
          datasetKind: "products",
          returnToTask: true,
          taskTitle: "SEEKWAY:US 全部 Listing 退货分析",
          store: "SEEKWAY:US",
          blockedCommentCount: 12,
          categoryOptions: [
            {
              category_a: "水鞋",
              category_b: "薄底水鞋",
              agent_family: "鞋履智能体",
            },
          ],
          unresolvedProducts: [
            {
              product_key: "SKU-1",
              msku: "SKU-1",
              product_name: "水鞋一",
              suggested_listing: "SK001",
              comment_count: 7,
              record_count: 8,
              issue: "product_not_found",
              editable: true,
            },
            {
              product_key: "SKU-2",
              msku: "SKU-2",
              product_name: "水鞋二",
              suggested_listing: "SK001",
              comment_count: 5,
              record_count: 5,
              issue: "product_not_found",
              editable: true,
            },
          ],
        }}
        taskDraft={{ form: { product_version_id: "products-v2" }, step: 3 }}
        onReturnToTask={onReturnToTask}
      />,
    );

    expect(
      await screen.findByText(
        "这里只显示阻断当前任务的商品，不需要在完整产品信息中搜索。",
      ),
    ).toBeVisible();
    expect(screen.getByText("SKU-1")).toBeVisible();
    expect(screen.getByText("SKU-2")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "选择当前 2 个" }));
    await user.selectOptions(screen.getByLabelText("批量设置品类"), "0");
    await user.click(screen.getByRole("button", { name: "应用到已选 2 个" }));
    await user.click(screen.getByRole("button", { name: "保存 2 个商品并重新预检" }));

    await waitFor(() =>
      expect(apiMock.completeProductCategories).toHaveBeenCalledWith(
        "products-dataset",
        expect.objectContaining({
          expected_version: 2,
          store: "SEEKWAY:US",
          items: [
            expect.objectContaining({
              msku: "SKU-1",
              listing: "SK001",
              category_a: "水鞋",
              category_b: "薄底水鞋",
            }),
            expect.objectContaining({
              msku: "SKU-2",
              listing: "SK001",
              category_a: "水鞋",
              category_b: "薄底水鞋",
            }),
          ],
        }),
      ),
    );
    expect(onReturnToTask).toHaveBeenCalledWith("products-v3");
  });

  test("已就绪片段排队时明确显示部分排队", async () => {
    const task = {
      id: "task-partial-queue",
      title: "混合品类退货分析",
      status: "queued",
      stage: "准备数据",
      message: "已就绪片段等待运行",
      revision: 1,
      progress_percent: 0,
      progress_current: 0,
      progress_total: 8,
      owner_name: "管理员",
      created_at: "2026-08-11T08:00:00Z",
      metrics: {},
      snapshot: {
        execution_plan: {
          unresolved_policy: "run_ready",
          summary: { blocked_count: 2 },
        },
      },
      segments: [],
    };
    apiMock.tasks.mockResolvedValue([task]);
    apiMock.task.mockResolvedValue(task);

    render(
      <TaskMonitor
        notify={vi.fn()}
        onNavigate={vi.fn()}
        onChanged={vi.fn()}
        focusId={null}
      />,
    );

    expect((await screen.findAllByText("部分排队")).length).toBeGreaterThan(0);
  });

  test("阻断任务可以重新预检并提交新的执行计划", async () => {
    const user = userEvent.setup();
    const task = {
      id: "task-replan",
      title: "阻断任务",
      status: "blocked",
      stage: "任务阻断",
      message: "商品维度需要修复",
      revision: 2,
      progress_percent: 0,
      progress_current: 0,
      progress_total: 8,
      owner_name: "管理员",
      created_at: "2026-08-11T08:00:00Z",
      dataset_name: "退货数据",
      dataset_version: 1,
      product_name: "商品维度",
      product_version: 2,
      product_version_id: "products-v2",
      connection_name: "生产线路",
      config_version: 1,
      primary_model: "gpt-main",
      primary_effort: "medium",
      metrics: {},
      snapshot: { execution_plan: { unresolved_policy: "block_all" } },
      segments: [],
    };
    apiMock.tasks.mockResolvedValue([task]);
    apiMock.task.mockResolvedValue(task);
    apiMock.preflightTaskReplan.mockResolvedValue(executionPlan);
    apiMock.replanTask.mockResolvedValue({
      ...task,
      status: "queued",
      revision: 3,
    });

    render(
      <TaskMonitor
        notify={vi.fn()}
        onNavigate={vi.fn()}
        onChanged={vi.fn()}
        focusId={task.id}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "重新预检 / 规划" }));
    expect(
      await screen.findByRole("heading", { name: "重新预检并规划" }),
    ).toBeVisible();
    await waitFor(() =>
      expect(apiMock.preflightTaskReplan).toHaveBeenCalledWith("task-replan", {
        product_version_id: "products-v2",
      }),
    );

    await user.type(screen.getByLabelText("重新规划原因"), "商品维度已修复");
    await user.click(screen.getByRole("button", { name: "提交新执行计划" }));

    await waitFor(() =>
      expect(apiMock.replanTask).toHaveBeenCalledWith("task-replan", {
        product_version_id: "products-v2",
        expected_revision: 2,
        plan_hash: "a".repeat(64),
        unresolved_policy: "block_all",
        reason: "商品维度已修复",
      }),
    );
  });

  test("密集进度事件只触发一次批量刷新", async () => {
    let eventSource;
    class EventSourceProbe {
      constructor() {
        this.listeners = new Map();
        eventSource = this;
      }

      addEventListener(type, listener) {
        this.listeners.set(type, listener);
      }

      emit(type, data) {
        this.listeners.get(type)?.({ data: JSON.stringify(data) });
      }

      close() {}
    }

    const originalEventSource = globalThis.EventSource;
    globalThis.EventSource = EventSourceProbe;
    const task = {
      id: "task-live-refresh",
      title: "实时进度任务",
      status: "running",
      stage: "语义分析",
      message: "正在执行",
      revision: 1,
      progress_percent: 10,
      progress_current: 1,
      progress_total: 10,
      owner_name: "管理员",
      created_at: "2026-08-12T08:00:00Z",
      metrics: {},
      snapshot: { execution_plan: { unresolved_policy: "run_ready" } },
      segments: [
        {
          id: "segment-kp006",
          segment_key: "SEEKWAY:US/KP006/footwear",
          agent_key: "footwear",
          agent_family: "鞋履智能体",
          scope: { store: "SEEKWAY:US", listing: "KP006" },
          status: "running",
          record_count: 12,
          unique_comments: 10,
          progress_current: 1,
          progress_total: 10,
          model_calls: 0,
          cache_hits: 0,
          variants: [],
        },
      ],
    };
    apiMock.tasks.mockResolvedValue([task]);
    apiMock.task.mockResolvedValue(task);
    const onChanged = vi.fn();

    try {
      render(
        <TaskMonitor
          notify={vi.fn()}
          onNavigate={vi.fn()}
          onChanged={onChanged}
          focusId={null}
        />,
      );
      expect(
        await screen.findByRole("heading", { name: "实时进度任务" }),
      ).toBeVisible();

      act(() => {
        for (let index = 1; index <= 12; index += 1) {
          eventSource.emit("task", {
            id: `event-${index}`,
            stage: "语义分析",
            message: `已完成 ${index} 组评论`,
            data: { segment_id: "segment-kp006" },
            created_at: "2026-08-12T08:01:00Z",
          });
        }
      });

      await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1), {
        timeout: 1200,
      });
      expect(apiMock.tasks).toHaveBeenCalledTimes(2);
      expect(apiMock.task).toHaveBeenCalledTimes(2);
      expect(screen.getByText("已完成 12 组评论")).toBeVisible();
      expect(screen.getAllByText("KP006 · Listing 分类")).toHaveLength(12);
    } finally {
      globalThis.EventSource = originalEventSource;
    }
  });

  test("已完成 Listing 可以直接查看和下载阶段结果", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    const completedSegment = {
      id: "segment-sr001",
      segment_key: "SEEKWAY:US/SR001/footwear",
      agent_key: "footwear",
      agent_family: "鞋履智能体",
      scope: { store: "SEEKWAY:US", listing: "SR001" },
      status: "completed",
      result_file_path: "runtime/results/sr001.xlsx",
      result_version_id: "classification-version-sr001",
      result_version: 1,
      result_publish_status: "published",
      result_quality_status: "ready",
      record_count: 12,
      unique_comments: 8,
      progress_current: 8,
      progress_total: 8,
      model_calls: 2,
      cache_hits: 1,
      variants: [{ category_a: "鞋履", category_b: "休闲运动水鞋" }],
      logic_version: "footwear-v2",
      taxonomy_version: "taxonomy-v3",
      execution_order: 1,
    };
    const task = {
      id: "task-listing-delivery",
      title: "Listing 交付任务",
      status: "running",
      stage: "语义分析",
      message: "其他 Listing 仍在运行",
      revision: 3,
      progress_percent: 50,
      progress_current: 8,
      progress_total: 16,
      owner_name: "管理员",
      created_at: "2026-08-12T08:00:00Z",
      dataset_name: "退货数据",
      dataset_version: 1,
      product_name: "商品维度",
      product_version: 1,
      connection_name: "生产线路",
      config_version: 1,
      primary_model: "gpt-main",
      primary_effort: "medium",
      metrics: {},
      snapshot: { execution_plan: { unresolved_policy: "run_ready" } },
      segments: [completedSegment],
    };
    apiMock.tasks.mockResolvedValue([task]);
    apiMock.task.mockResolvedValue(task);

    render(
      <TaskMonitor
        notify={vi.fn()}
        onNavigate={onNavigate}
        onChanged={vi.fn()}
        focusId={null}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "查看分类结果" }));
    expect(onNavigate).toHaveBeenCalledWith("classification-results", {
      kind: "classification-result",
      id: "classification-version-sr001",
      taskId: "task-listing-delivery",
      segmentId: "segment-sr001",
      listing: "SR001",
    });
    expect(screen.getByRole("link", { name: "下载" })).toHaveAttribute(
      "href",
      "/classification-download",
    );
    expect(screen.getByText("任务配置")).toBeVisible();
    expect(screen.queryByText("任务快照")).not.toBeInTheDocument();
    expect(screen.getAllByText("Listing 分类").length).toBeGreaterThan(0);
    expect(screen.getByText("发布分类版本")).toBeVisible();
    expect(screen.getByText("任务结束")).toBeVisible();
  });

  test("模型服务连续失败会显示请求明细和恢复入口", async () => {
    const task = {
      id: "task-model-service-paused",
      title: "模型服务保护任务",
      status: "paused",
      stage: "模型服务异常",
      message: "模型服务连续失败，任务已自动暂停",
      pause_requested: 1,
      revision: 2,
      progress_percent: 4,
      progress_current: 4,
      progress_total: 100,
      owner_name: "管理员",
      created_at: "2026-08-14T08:00:00Z",
      metrics: {},
      snapshot: { execution_plan: { unresolved_policy: "run_ready" } },
      segments: [
        {
          id: "segment-model-service-paused",
          segment_key: "SEEKWAY:US/SK001/footwear",
          agent_key: "footwear",
          agent_family: "鞋履智能体",
          scope: { store: "SEEKWAY:US", listing: "SK001" },
          status: "paused",
          record_count: 100,
          unique_comments: 100,
          progress_current: 4,
          progress_total: 100,
          model_calls: 0,
          model_failures: 5,
          cache_hits: 0,
          error: "模型服务连续失败，任务已自动暂停；请检查连接后继续执行",
          taxonomy_version: "footwear-taxonomy-v1",
          variants: [],
        },
      ],
    };
    apiMock.tasks.mockResolvedValue([task]);
    apiMock.task.mockResolvedValue(task);

    const { container } = render(
      <TaskMonitor
        notify={vi.fn()}
        onNavigate={vi.fn()}
        onChanged={vi.fn()}
        focusId={null}
      />,
    );

    expect(await screen.findByText("模型服务异常，任务已自动暂停")).toBeVisible();
    expect(screen.getByText("5 次请求")).toBeVisible();
    expect(screen.getByText("成功 0 · 失败 5")).toBeVisible();
    expect(screen.getByText("下一步：继续全部后恢复执行")).toBeVisible();
    expect(
      within(container.querySelector(".task-detail-header")).queryByText("已暂停"),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "继续全部" })).toBeVisible();
  });

  test("审计任务目标会打开并高亮对应 Listing 片段", async () => {
    const scrollProbe = vi.spyOn(globalThis.HTMLElement.prototype, "scrollIntoView");
    const segment = {
      id: "segment-sr001",
      segment_key: "SEEKWAY:US/SR001/footwear",
      agent_key: "footwear",
      agent_family: "鞋履智能体",
      scope: { store: "SEEKWAY:US", listing: "SR001" },
      status: "running",
      record_count: 12,
      unique_comments: 8,
      progress_current: 2,
      progress_total: 8,
      model_calls: 1,
      cache_hits: 0,
      variants: [],
      execution_order: 1,
    };
    const task = {
      id: "task-segment-focus",
      title: "片段定位任务",
      status: "running",
      stage: "语义分析",
      message: "正在运行",
      revision: 1,
      progress_percent: 25,
      progress_current: 2,
      progress_total: 8,
      owner_name: "管理员",
      created_at: "2026-08-12T08:00:00Z",
      metrics: {},
      snapshot: { execution_plan: { unresolved_policy: "run_ready" } },
      segments: [segment],
    };
    apiMock.tasks.mockResolvedValue([task]);
    apiMock.task.mockResolvedValue(task);

    render(
      <TaskMonitor
        notify={vi.fn()}
        onNavigate={vi.fn()}
        onChanged={vi.fn()}
        focusId="task-segment-focus"
        focusSegmentId="segment-sr001"
      />,
    );

    const row = await screen.findByRole("row", { name: /SR001/ });
    expect(row).toHaveClass("is-targeted");
    expect(row).toHaveAttribute("aria-current", "true");
    await waitFor(() => expect(scrollProbe).toHaveBeenCalled());
    scrollProbe.mockRestore();
  });

  test("Listing 结果发布状态矩阵限制查看、下载和重试入口", async () => {
    const user = userEvent.setup();
    const baseSegment = {
      agent_key: "footwear",
      agent_family: "鞋履智能体",
      status: "completed",
      record_count: 12,
      unique_comments: 8,
      progress_current: 8,
      progress_total: 8,
      model_calls: 2,
      cache_hits: 1,
      variants: [{ category_a: "鞋履", category_b: "休闲运动水鞋" }],
      logic_version: "footwear-v2",
      taxonomy_version: "taxonomy-v3",
    };
    const task = {
      id: "task-publish-matrix",
      title: "结果发布状态矩阵",
      status: "running",
      stage: "生成结果",
      message: "正在发布 Listing 结果",
      revision: 3,
      progress_percent: 100,
      progress_current: 24,
      progress_total: 24,
      owner_name: "管理员",
      created_at: "2026-08-12T08:00:00Z",
      dataset_name: "退货数据",
      dataset_version: 1,
      product_name: "商品维度",
      product_version: 1,
      connection_name: "生产线路",
      config_version: 1,
      primary_model: "gpt-main",
      primary_effort: "medium",
      metrics: {},
      snapshot: { execution_plan: { unresolved_policy: "run_ready" } },
      segments: [
        {
          ...baseSegment,
          id: "segment-publishing",
          segment_key: "SEEKWAY:US/PUBLISHING/footwear",
          scope: { store: "SEEKWAY:US", listing: "PUBLISHING" },
          result_publish_status: "publishing",
          result_version_id: null,
          execution_order: 1,
        },
        {
          ...baseSegment,
          id: "segment-publish-failed",
          segment_key: "SEEKWAY:US/FAILED/footwear",
          scope: { store: "SEEKWAY:US", listing: "FAILED" },
          result_publish_status: "failed",
          result_publish_error: "发布服务暂不可用\ntrace id: publish-42",
          result_version_id: null,
          execution_order: 2,
        },
        {
          ...baseSegment,
          id: "segment-published",
          segment_key: "SEEKWAY:US/PUBLISHED/footwear",
          scope: { store: "SEEKWAY:US", listing: "PUBLISHED" },
          result_publish_status: "published",
          result_quality_status: "ready",
          result_version_id: "classification-version-published",
          execution_order: 3,
        },
        {
          ...baseSegment,
          id: "segment-review-required",
          segment_key: "SEEKWAY:US/REVIEW/footwear",
          scope: { store: "SEEKWAY:US", listing: "REVIEW" },
          result_publish_status: "published",
          result_quality_status: "review_required",
          result_version_id: "classification-version-review",
          execution_order: 4,
        },
        {
          ...baseSegment,
          id: "segment-unusable",
          segment_key: "SEEKWAY:US/UNUSABLE/footwear",
          scope: { store: "SEEKWAY:US", listing: "UNUSABLE" },
          result_publish_status: "published",
          result_quality_status: "unusable",
          result_version_id: "classification-version-unusable",
          execution_order: 5,
        },
      ],
    };
    apiMock.tasks.mockResolvedValue([task]);
    apiMock.task.mockResolvedValue(task);
    apiMock.retrySegmentResultPublish.mockResolvedValue(task);

    render(
      <TaskMonitor
        notify={vi.fn()}
        onNavigate={vi.fn()}
        onChanged={vi.fn()}
        focusId={null}
      />,
    );

    const publishingRow = await screen.findByRole("row", { name: /PUBLISHING/ });
    expect(within(publishingRow).getByText("正在生成结果")).toBeVisible();
    expect(
      within(publishingRow).getByRole("button", { name: "查看分类结果" }),
    ).toBeDisabled();
    expect(within(publishingRow).getByRole("button", { name: "下载" })).toBeDisabled();

    const failedRow = screen.getByRole("row", { name: /FAILED/ });
    expect(within(failedRow).getByText("结果生成失败")).toBeVisible();
    expect(
      within(failedRow).getByText("发布服务暂不可用 trace id: publish-42"),
    ).toBeVisible();
    expect(
      within(failedRow).getByRole("button", { name: "重试生成结果" }),
    ).toBeEnabled();
    await user.click(within(failedRow).getByRole("button", { name: "重试生成结果" }));
    expect(apiMock.retrySegmentResultPublish).toHaveBeenCalledWith(
      "task-publish-matrix",
      "segment-publish-failed",
      {
        expected_revision: 3,
        reason: "重新发布分类结果",
      },
    );

    const publishedRow = screen.getByRole("row", { name: /PUBLISHED/ });
    expect(within(publishedRow).getByText("可用")).toBeVisible();
    expect(within(publishedRow).getByText("版本发布：已发布")).toBeVisible();
    expect(
      within(publishedRow).getByRole("button", { name: "查看分类结果" }),
    ).toBeEnabled();
    expect(within(publishedRow).getByRole("link", { name: "下载" })).toBeVisible();

    const reviewRow = screen.getByRole("row", { name: /REVIEW/ });
    expect(within(reviewRow).getByText("需复核")).toBeVisible();
    expect(within(reviewRow).getByText("版本发布：已发布")).toBeVisible();
    expect(
      within(reviewRow).getByRole("button", { name: "查看分类结果" }),
    ).toBeEnabled();

    const unusableRow = screen.getByRole("row", { name: /UNUSABLE/ });
    expect(within(unusableRow).getByText("不可用")).toBeVisible();
    expect(within(unusableRow).getByText("版本发布：已发布")).toBeVisible();
    expect(
      within(unusableRow).getByRole("button", { name: "查看分类结果" }),
    ).toBeEnabled();
  });

  test("旧 Listing 没有结果版本引用时只提供旧结果下载", async () => {
    const legacySegment = {
      id: "segment-legacy",
      segment_key: "SEEKWAY:US/SR001/footwear",
      agent_key: "footwear",
      agent_family: "鞋履智能体",
      scope: { store: "SEEKWAY:US", listing: "SR001" },
      status: "completed",
      result_version_id: null,
      result_file_path: "runtime/results/legacy-sr001.xlsx",
      record_count: 12,
      unique_comments: 8,
      progress_current: 8,
      progress_total: 8,
      model_calls: 2,
      cache_hits: 1,
      variants: [{ category_a: "鞋履", category_b: "休闲运动水鞋" }],
      logic_version: "footwear-v1",
      taxonomy_version: "taxonomy-v2",
      execution_order: 1,
    };
    const task = {
      id: "task-legacy-listing",
      title: "旧 Listing 结果",
      status: "completed",
      stage: "分析完成",
      message: "任务已完成",
      revision: 1,
      progress_percent: 100,
      progress_current: 8,
      progress_total: 8,
      owner_name: "管理员",
      created_at: "2026-08-12T08:00:00Z",
      dataset_name: "退货数据",
      dataset_version: 1,
      product_name: "商品维度",
      product_version: 1,
      connection_name: "历史线路",
      config_version: 1,
      primary_model: "gpt-main",
      primary_effort: "medium",
      metrics: {},
      snapshot: { execution_plan: { unresolved_policy: "run_ready" } },
      segments: [legacySegment],
    };
    apiMock.tasks.mockResolvedValue([task]);
    apiMock.task.mockResolvedValue(task);

    render(
      <TaskMonitor
        notify={vi.fn()}
        onNavigate={vi.fn()}
        onChanged={vi.fn()}
        focusId={task.id}
      />,
    );

    expect(await screen.findAllByRole("link", { name: "下载旧结果" })).toHaveLength(2);
    expect(
      screen.queryByRole("button", { name: "查看分类结果" }),
    ).not.toBeInTheDocument();
  });

  test("已暂停 Listing 可以继续并提交取消原因", async () => {
    const user = userEvent.setup();
    const pausedSegment = {
      segment_key: "SEEKWAY:US/SK001/footwear",
      agent_key: "footwear",
      agent_family: "鞋履智能体",
      scope: { store: "SEEKWAY:US", listing: "SK001" },
      status: "paused",
      record_count: 12,
      unique_comments: 8,
      progress_current: 4,
      progress_total: 8,
      model_calls: 2,
      cache_hits: 1,
      variants: [{ category_a: "鞋履", category_b: "薄底水鞋" }],
      logic_version: "footwear-v2",
      taxonomy_version: "taxonomy-v3",
      execution_order: 1,
    };
    const task = {
      id: "task-segment-controls",
      title: "Listing 控制任务",
      status: "paused",
      stage: "已暂停",
      message: "未完成 Listing 已暂停",
      revision: 3,
      progress_percent: 50,
      progress_current: 4,
      progress_total: 8,
      owner_name: "管理员",
      created_at: "2026-08-12T08:00:00Z",
      metrics: {},
      snapshot: { execution_plan: { unresolved_policy: "run_ready" } },
      segments: [pausedSegment],
    };
    const queuedTask = {
      ...task,
      status: "queued",
      revision: 4,
      segments: [{ ...pausedSegment, status: "queued" }],
    };
    const cancelledTask = {
      ...task,
      status: "cancelled",
      revision: 5,
      segments: [{ ...pausedSegment, status: "cancelled" }],
    };
    apiMock.tasks.mockResolvedValue([task]);
    apiMock.task.mockResolvedValue(task);
    apiMock.controlTaskSegment
      .mockResolvedValueOnce(queuedTask)
      .mockResolvedValueOnce(cancelledTask);

    render(
      <TaskMonitor
        notify={vi.fn()}
        onNavigate={vi.fn()}
        onChanged={vi.fn()}
        focusId={null}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "继续" }));
    await waitFor(() =>
      expect(apiMock.controlTaskSegment).toHaveBeenNthCalledWith(
        1,
        task.id,
        pausedSegment.segment_key,
        "resume",
        { expected_revision: 3, note: "" },
      ),
    );

    await user.click(screen.getByRole("button", { name: "取消" }));
    expect(screen.getByRole("button", { name: "取消" })).toHaveClass(
      "secondary-button",
      "compact-button",
      "listing-cancel-button",
    );
    expect(screen.getByRole("dialog", { name: "取消 SK001" })).toBeVisible();
    await user.type(screen.getByLabelText("取消原因"), "不再需要该 Listing");
    await user.click(screen.getByRole("button", { name: "确认取消 Listing" }));
    await waitFor(() =>
      expect(apiMock.controlTaskSegment).toHaveBeenNthCalledWith(
        2,
        task.id,
        pausedSegment.segment_key,
        "cancel",
        { expected_revision: 4, note: "不再需要该 Listing" },
      ),
    );
  });

  test("取消任务保留部分结果并可继续未完成 Listing", async () => {
    const user = userEvent.setup();
    const task = {
      id: "task-cancelled-partial",
      title: "多 Listing 退货分析",
      status: "cancelled",
      stage: "已取消（有部分结果）",
      message: "已保留 1 个完成片段的部分结果",
      revision: 7,
      result_file_path: "runtime/results/task/analysis-partial-v1.xlsx",
      progress_percent: 50,
      progress_current: 6,
      progress_total: 12,
      owner_name: "管理员",
      created_at: "2026-08-11T08:00:00Z",
      dataset_name: "退货数据",
      dataset_version: 1,
      product_name: "商品维度",
      product_version: 1,
      connection_name: "生产线路",
      config_version: 1,
      primary_model: "gpt-main",
      primary_effort: "medium",
      metrics: { records: 12, unique_comments: 12, review_count: 0 },
      snapshot: { execution_plan: { unresolved_policy: "run_ready" } },
      segments: [
        {
          id: "segment-completed-sk001",
          segment_key: "footwear:SK001",
          agent_key: "footwear",
          agent_family: "鞋履智能体",
          scope: { store: "SEEKWAY:US", listing: "SK001" },
          status: "completed",
          result_version_id: "classification-version-sk001",
          result_publish_status: "published",
          result_quality_status: "ready",
          record_count: 6,
          unique_comments: 6,
          progress_current: 6,
          progress_total: 6,
          model_calls: 1,
          cache_hits: 0,
          variants: [],
        },
        {
          segment_key: "footwear:SK002",
          agent_key: "footwear",
          agent_family: "鞋履智能体",
          scope: { store: "SEEKWAY:US", listing: "SK002" },
          status: "cancelled",
          record_count: 6,
          unique_comments: 6,
          progress_current: 0,
          progress_total: 6,
          model_calls: 0,
          cache_hits: 0,
          variants: [],
        },
      ],
    };
    apiMock.tasks.mockResolvedValue([task]);
    apiMock.task.mockResolvedValue(task);
    apiMock.downloadUrl.mockReturnValue("/partial-download");
    apiMock.resumeTask.mockResolvedValue({ ...task, status: "queued", revision: 8 });

    render(
      <TaskMonitor
        notify={vi.fn()}
        onNavigate={vi.fn()}
        onChanged={vi.fn()}
        focusId={task.id}
      />,
    );

    expect(await screen.findAllByText("已取消（有部分结果）")).not.toHaveLength(0);
    expect(screen.getByRole("link", { name: "下载部分结果" })).toHaveAttribute(
      "href",
      "/partial-download",
    );
    expect(screen.getByText("已取消")).toBeVisible();
    expect(
      screen.getByText("批量任务已取消，已完成 Listing 的分类结果仍然保留"),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "查看分类结果" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "重新排队未完成" }));
    await user.type(screen.getByLabelText("重新排队原因"), "补齐剩余 Listing");
    const resumeButtons = screen.getAllByRole("button", {
      name: "重新排队未完成片段",
    });
    await user.click(resumeButtons[resumeButtons.length - 1]);

    await waitFor(() =>
      expect(apiMock.resumeTask).toHaveBeenCalledWith("task-cancelled-partial", {
        expected_revision: 7,
        note: "补齐剩余 Listing",
      }),
    );
  });

  test("任务片段只对允许状态提供重试并显示 409 页面状态", async () => {
    const user = userEvent.setup();
    const task = {
      id: "task-1",
      title: "异常片段任务",
      status: "failed",
      stage: "语义分析",
      message: "片段执行失败",
      revision: 4,
      progress_percent: 50,
      progress_current: 4,
      progress_total: 8,
      owner_name: "管理员",
      created_at: "2026-08-10T08:00:00Z",
      dataset_name: "退货数据",
      dataset_version: 1,
      product_name: "商品维度",
      product_version: 1,
      product_version_id: "products-v1",
      connection_name: "生产线路",
      config_version: 1,
      primary_model: "gpt-main",
      primary_effort: "medium",
      metrics: {},
      snapshot: { execution_plan: { unresolved_policy: "run_ready" } },
      segments: [
        {
          segment_key: "footwear",
          agent_key: "footwear",
          agent_family: "鞋履智能体",
          scope: { store: "SEEKWAY:US", listing: "SK001" },
          logic_version: "footwear-v2",
          taxonomy_version: "taxonomy-v3",
          status: "failed",
          record_count: 12,
          unique_comments: 8,
          progress_current: 4,
          progress_total: 8,
          model_calls: 4,
          cache_hits: 1,
          error: "上游超时",
          variants: [{ category_a: "鞋履", category_b: "薄底水鞋", record_count: 12 }],
        },
        {
          segment_key: "unknown",
          agent_key: "unknown",
          agent_family: "未配置品类",
          logic_version: null,
          taxonomy_version: "unresolved-category-v1",
          status: "blocked",
          record_count: 3,
          unique_comments: 2,
          progress_current: 0,
          progress_total: 2,
          model_calls: 0,
          cache_hits: 0,
          error: null,
          variants: [{ category_a: "鞋履", category_b: "未知鞋型", record_count: 3 }],
        },
      ],
    };
    apiMock.tasks.mockResolvedValue([task]);
    apiMock.task.mockResolvedValue(task);
    apiMock.retryTaskSegment.mockRejectedValue(
      Object.assign(new Error("任务已被他人修改"), { status: 409 }),
    );

    render(
      <TaskMonitor
        notify={vi.fn()}
        onNavigate={vi.fn()}
        onChanged={vi.fn()}
        focusId={task.id}
      />,
    );

    expect((await screen.findAllByText("SK001")).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "重试" })).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "重试" }));
    await user.type(screen.getByLabelText("重试原因"), "确认上游恢复后重试");
    await user.click(screen.getByRole("button", { name: "确认重试片段" }));

    await waitFor(() =>
      expect(apiMock.retryTaskSegment).toHaveBeenCalledWith("task-1", "footwear", {
        expected_revision: 4,
        reason: "确认上游恢复后重试",
      }),
    );
    expect(
      await screen.findByText("任务版本已变化，请查看刷新后的片段状态再操作。"),
    ).toBeVisible();
  });

  test("运行中可以调整等待 Listing 的执行顺序", async () => {
    const user = userEvent.setup();
    const baseSegment = {
      agent_key: "footwear",
      agent_family: "鞋履智能体",
      logic_version: "footwear-v2",
      taxonomy_version: "taxonomy-v3",
      record_count: 12,
      unique_comments: 8,
      progress_current: 0,
      progress_total: 8,
      model_calls: 0,
      cache_hits: 0,
      error: null,
      variants: [{ category_a: "鞋履", category_b: "薄底水鞋", record_count: 12 }],
    };
    const task = {
      id: "task-order",
      title: "Listing 顺序任务",
      status: "running",
      stage: "语义分析",
      message: "正在执行",
      revision: 4,
      progress_percent: 10,
      progress_current: 1,
      progress_total: 24,
      owner_name: "管理员",
      created_at: "2026-08-10T08:00:00Z",
      dataset_name: "退货数据",
      dataset_version: 1,
      product_name: "商品维度",
      product_version: 1,
      connection_name: "生产线路",
      config_version: 1,
      primary_model: "gpt-main",
      primary_effort: "medium",
      metrics: {},
      snapshot: { execution_plan: { unresolved_policy: "run_ready" } },
      segments: [
        {
          ...baseSegment,
          segment_key: "segment-1",
          status: "running",
          execution_order: 1,
          scope: { store: "SEEKWAY:US", listing: "SK001" },
        },
        {
          ...baseSegment,
          segment_key: "segment-2",
          status: "queued",
          execution_order: 2,
          scope: { store: "SEEKWAY:US", listing: "SK002" },
        },
        {
          ...baseSegment,
          segment_key: "segment-3",
          status: "queued",
          execution_order: 3,
          scope: { store: "SEEKWAY:US", listing: "SK003" },
        },
      ],
    };
    const reordered = {
      ...task,
      revision: 5,
      segments: [
        task.segments[0],
        { ...task.segments[2], execution_order: 2 },
        { ...task.segments[1], execution_order: 3 },
      ],
    };
    apiMock.tasks.mockResolvedValue([task]);
    apiMock.task.mockResolvedValue(task);
    apiMock.reorderTaskSegments.mockResolvedValue(reordered);

    render(
      <TaskMonitor
        notify={vi.fn()}
        onNavigate={vi.fn()}
        onChanged={vi.fn()}
        focusId={null}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "置顶 SK003" }));

    await waitFor(() =>
      expect(apiMock.reorderTaskSegments).toHaveBeenCalledWith("task-order", {
        expected_revision: 4,
        segment_keys: ["segment-3", "segment-2"],
      }),
    );
    expect((await screen.findAllByText("SK003")).length).toBeGreaterThan(0);
  });

  test("用户可以导入新的产品信息", async () => {
    const user = userEvent.setup();
    apiMock.createDataset.mockResolvedValue({ id: "dataset-1" });

    const { container } = render(
      <DataManagement notify={vi.fn()} onNavigate={vi.fn()} focus={null} />,
    );

    await user.click(await screen.findByRole("button", { name: "导入产品信息" }));
    await user.type(screen.getByLabelText("产品信息名称"), "SEEKWAY 产品信息");
    await user.type(screen.getByLabelText("版本说明"), "首次导入产品信息");
    const fileInput = container.querySelector('input[type="file"]');
    await user.upload(fileInput, new File(["products"], "products.xlsx"));
    await user.click(screen.getByRole("button", { name: "创建不可变版本" }));

    await waitFor(() => expect(apiMock.createDataset).toHaveBeenCalledOnce());
    const body = apiMock.createDataset.mock.calls[0][0];
    expect(body.get("name")).toBe("SEEKWAY 产品信息");
    expect(body.get("kind")).toBe("products");
    expect(body.get("change_note")).toBe("首次导入产品信息");
  });

  test("用户提交复核后写入修改说明和版本号", async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn();
    const row = {
      id: "review-1",
      task_title: "US站退货分析",
      owner_name: "管理员",
      comment: "鞋码偏大",
      updated_at: "2026-08-10T08:00:00Z",
      classification: { status: "MANUAL_REVIEW" },
    };
    const detail = {
      ...row,
      workflow_status: "pending",
      revision: 3,
      revisions: [],
      classification: {
        status: "MANUAL_REVIEW",
        model_name: "gpt-main",
        semantic_units: [{ evidence: "鞋码偏大" }],
        primary_label_codes: ["size_large"],
        problem_label_codes: ["size_large"],
        review_reasons: ["需要人工确认"],
        taxonomy_version: "v1",
      },
    };
    apiMock.reviews.mockResolvedValue([row]);
    apiMock.review.mockResolvedValue(detail);
    apiMock.taxonomy.mockResolvedValue({
      labels: [{ code: "size_large", name: "尺码偏大" }],
    });
    apiMock.resolveReview.mockResolvedValue({});

    render(<ReviewCenter notify={vi.fn()} onChanged={onChanged} focus={null} />);

    expect(await screen.findByText("客户评论原文")).toBeVisible();
    await user.type(
      screen.getByPlaceholderText("必填：说明判断依据，便于后续追溯"),
      "证据明确，确认模型标签",
    );
    await user.click(screen.getByRole("button", { name: /确认并完成复核/ }));

    await waitFor(() =>
      expect(apiMock.resolveReview).toHaveBeenCalledWith("review-1", {
        expected_revision: 3,
        label_code: "size_large",
        note: "证据明确，确认模型标签",
      }),
    );
    expect(onChanged).toHaveBeenCalled();
  });

  test("旧复核审计目标按 workflow_status 打开指定记录", async () => {
    const row = {
      id: "review-2",
      task_title: "历史任务复核",
      owner_name: "管理员",
      comment: "指定历史复核记录",
      updated_at: "2026-08-10T08:00:00Z",
      workflow_status: "resolved",
      revision: 2,
      revisions: [],
      classification: {
        status: "MANUAL_REVIEW",
        primary_label_codes: [],
        problem_label_codes: [],
      },
    };
    apiMock.reviews.mockImplementation((status) =>
      Promise.resolve(status === "resolved" ? [row] : []),
    );
    apiMock.review.mockResolvedValue(row);
    apiMock.taxonomy.mockResolvedValue({ labels: [] });

    render(
      <ReviewCenter
        notify={vi.fn()}
        onChanged={vi.fn()}
        focus={{ kind: "review", id: "review-2", status: "resolved" }}
      />,
    );

    expect(await screen.findByText("指定历史复核记录")).toBeVisible();
    expect(screen.getByRole("button", { name: "已处理" })).toHaveClass("active");
    expect(apiMock.review).toHaveBeenCalledWith("review-2");
  });

  test("用户可以从模型列表启动真实验证", async () => {
    const user = userEvent.setup();
    const version = {
      id: "cfg-1",
      connection_id: "conn-1",
      version: 1,
      base_url: "https://api.example.com/v1",
      primary_model: "gpt-main",
      primary_effort: "medium",
      cheap_model: null,
      cheap_effort: "low",
      secondary_model: null,
      secondary_effort: "high",
      requests_per_minute: 60,
      max_workers: 4,
      timeout_seconds: 120,
      cheap_audit_percent: 5,
      validation_status: "validated",
      validation_message: "验证通过",
      change_note: "初始配置",
      creator_name: "管理员",
      created_at: "2026-08-10T08:00:00Z",
      validated_at: "2026-08-10T08:00:00Z",
    };
    apiMock.configs.mockResolvedValue([
      {
        id: "conn-1",
        name: "生产线路",
        provider: "responses-compatible",
        active_version_id: "cfg-1",
        active_version: version,
        versions: [version],
        models: [
          {
            id: "model-1",
            connection_id: "conn-1",
            model_key: "gpt-main",
            display_name: "主分析模型",
            supported_efforts: ["medium"],
            active: true,
            validation_status: "validated",
            validation_message: "验证通过",
          },
        ],
      },
    ]);
    apiMock.startModelValidation.mockResolvedValue({
      id: "validation-1",
      kind: "model",
      target_id: "model-1",
      status: "queued",
      stage: "queued",
      total_count: 1,
      completed_count: 0,
      created_at: "2026-08-10T08:00:00Z",
      endpoint: "https://api.example.com/v1/responses",
      timeout_seconds: 120,
      created_by_name: "管理员",
      items: [
        {
          model_id: "model-1",
          model_key: "gpt-main",
          display_name: "主分析模型",
          role: "单模型验证",
          effort: "medium",
          status: "pending",
          message: "等待验证",
          started_at: null,
          duration_ms: null,
          http_status: null,
        },
      ],
    });

    render(<ApiManagement notify={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "模型服务" })).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "智能体模型策略" }),
    ).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: /管理目录/ }));
    expect(screen.getByRole("heading", { name: "可用模型" })).toBeVisible();
    expect(screen.getAllByRole("button", { name: "添加模型" })).toHaveLength(1);
    expect(screen.queryByText("连接信息")).not.toBeInTheDocument();
    expect((await screen.findAllByText("gpt-main"))[0]).toBeVisible();
    await user.click(screen.getByRole("button", { name: "验证" }));

    await waitFor(() =>
      expect(apiMock.startModelValidation).toHaveBeenCalledWith("model-1"),
    );
    expect((await screen.findAllByText("单模型验证"))[0]).toBeVisible();
  });

  test("模型服务仅保留接入方同步后的可用模型", async () => {
    const user = userEvent.setup();
    const version = {
      id: "cfg-1",
      connection_id: "conn-1",
      version: 1,
      base_url: "https://api.example.com/v1",
      primary_model: "provider-model",
      primary_effort: "medium",
      validation_status: "validated",
    };
    const connection = (models) => [
      {
        id: "conn-1",
        name: "生产线路",
        provider: "responses-compatible",
        active_version_id: "cfg-1",
        active_version: version,
        versions: [version],
        models,
      },
    ];
    apiMock.configs
      .mockResolvedValueOnce(
        connection([
          {
            id: "model-old",
            model_key: "gpt-5.6",
            display_name: "gpt-5.6",
            supported_efforts: ["medium"],
            active: true,
            validation_status: "validated",
          },
        ]),
      )
      .mockResolvedValueOnce(
        connection([
          {
            id: "model-old",
            model_key: "gpt-5.6",
            display_name: "gpt-5.6",
            supported_efforts: ["medium"],
            active: false,
            validation_status: "validated",
          },
          {
            id: "model-provider",
            model_key: "provider-model",
            display_name: "provider-model",
            supported_efforts: ["medium"],
            active: true,
            validation_status: "draft",
          },
        ]),
      );
    apiMock.discoverModels.mockResolvedValue({ count: 1 });

    render(<ApiManagement notify={vi.fn()} />);

    await user.click(await screen.findByRole("button", { name: "同步目录" }));
    await waitFor(() => expect(apiMock.discoverModels).toHaveBeenCalledWith("conn-1"));
    expect(await screen.findByText("provider-model")).toBeVisible();
    expect(screen.queryByText("gpt-5.6")).not.toBeInTheDocument();
  });

  test("用户设置首屏使用用户与安全标题", async () => {
    render(
      <TeamPage
        notify={vi.fn()}
        currentUser={{ id: "user-1", display_name: "管理员" }}
      />,
    );

    expect(await screen.findByRole("heading", { name: "用户与安全" })).toBeVisible();
    expect(screen.getByText("用户账号")).toBeVisible();
    expect(screen.getByText("账号安全")).toBeVisible();
  });

  test("用户与安全仅在表单完成后启用主操作", async () => {
    const user = userEvent.setup();
    render(
      <TeamPage
        notify={vi.fn()}
        currentUser={{ id: "user-1", display_name: "管理员" }}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "新增用户" }));
    const createButton = await screen.findByRole("button", {
      name: "创建用户",
    });
    expect(createButton).toBeDisabled();
    expect(screen.getByText("请填写姓名。")).toBeVisible();

    await user.type(screen.getByLabelText("姓名"), "测试成员");
    await user.type(screen.getByLabelText("邮箱"), "invalid-email");
    await user.type(screen.getByLabelText(/^初始密码/), "1234567890");
    expect(createButton).toBeDisabled();
    expect(screen.getByText("请填写有效邮箱。")).toBeVisible();

    await user.clear(screen.getByLabelText("邮箱"));
    await user.type(screen.getByLabelText("邮箱"), "member@example.com");
    expect(createButton).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "取消" }));
    await user.click(screen.getByRole("button", { name: "修改我的密码" }));
    const updatePasswordButton = await screen.findByRole("button", {
      name: "保存并重新登录",
    });
    expect(updatePasswordButton).toBeDisabled();
    expect(screen.getByText("请填写当前密码。")).toBeVisible();

    await user.type(screen.getByLabelText("当前密码"), "old-password");
    await user.type(screen.getByLabelText(/^新密码/), "123456789");
    expect(updatePasswordButton).toBeDisabled();
    expect(screen.getByText("新密码至少 10 位。")).toBeVisible();

    await user.type(screen.getByLabelText(/^新密码/), "0");
    expect(updatePasswordButton).toBeEnabled();
  });

  test("我的模型偏好不再编辑初筛抽检比例", async () => {
    const user = userEvent.setup();
    apiMock.configs.mockResolvedValue([
      {
        id: "conn-1",
        name: "模型服务",
        active_version_id: "cfg-1",
        active_version: {
          id: "cfg-1",
          cheap_audit_percent: 11,
        },
        models: [
          {
            id: "model-1",
            model_key: "gpt-main",
            display_name: "主分析模型",
            supported_efforts: ["medium"],
            active: true,
            validation_status: "validated",
          },
        ],
      },
    ]);
    apiMock.modelPreference.mockResolvedValue({
      connection_id: "conn-1",
      cheap_model: null,
      cheap_effort: "low",
      primary_model: "gpt-main",
      primary_effort: "medium",
      secondary_model: null,
      secondary_effort: "high",
      cheap_audit_percent: 67,
    });
    apiMock.saveModelPreference.mockResolvedValue({
      connection_id: "conn-1",
      primary_model: "gpt-main",
      primary_effort: "medium",
      cheap_audit_percent: 11,
    });

    render(<ModelPreferencePage notify={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "我的模型偏好" })).toBeVisible();
    expect(screen.queryByLabelText(/初筛抽检比例/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "保存为我的默认策略" }));

    expect(apiMock.saveModelPreference).toHaveBeenCalledWith(
      expect.objectContaining({ cheap_audit_percent: 11 }),
    );
  });

  test("旧 API 与模型标签统一进入模型服务且只高亮一个子导航", async () => {
    const { rerender } = render(
      <SystemSettingsPage
        route={{ query: { tab: "api" } }}
        notify={vi.fn()}
        currentUser={{ id: "user-1", is_admin: true }}
      />,
    );

    expect(screen.getByRole("button", { name: "模型服务" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.queryByRole("button", { name: "API 接入" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "模型管理" })).not.toBeInTheDocument();

    rerender(
      <SystemSettingsPage
        route={{ query: { tab: "models" } }}
        notify={vi.fn()}
        currentUser={{ id: "user-1", is_admin: true }}
      />,
    );
    expect(
      screen.getAllByRole("button").filter((item) => item.ariaCurrent),
    ).toHaveLength(1);
    expect(screen.getByRole("button", { name: "模型服务" })).toHaveClass("active");
  });

  test("模型服务摘要展示未发布草稿并保留按需编辑入口", async () => {
    const user = userEvent.setup();
    const activeVersion = {
      id: "cfg-1",
      connection_id: "conn-1",
      version: 1,
      base_url: "https://api.example.com/v1",
      primary_model: "gpt-main",
      primary_effort: "medium",
      cheap_model: "gpt-cheap",
      cheap_effort: "low",
      secondary_model: "gpt-review",
      secondary_effort: "high",
      validation_status: "validated",
      validated_at: "2026-08-10T08:00:00Z",
      published_at: "2026-08-10T08:10:00Z",
    };
    const draftVersion = {
      ...activeVersion,
      id: "cfg-2",
      version: 2,
      validation_status: "failed",
      validation_message: "验证失败",
      change_note: "调整风险复核模型",
      published_at: null,
    };
    apiMock.configs.mockResolvedValue([
      {
        id: "conn-1",
        name: "生产模型服务",
        provider: "responses-compatible",
        active_version_id: "cfg-1",
        active_version: activeVersion,
        versions: [draftVersion, activeVersion],
        models: [],
      },
    ]);

    render(<ApiManagement notify={vi.fn()} />);

    expect(await screen.findByText("草稿 #2 · 验证失败")).toBeVisible();
    expect(screen.getByText(/当前运行 #1 不受影响/)).toBeVisible();
    expect(screen.getByRole("button", { name: "继续处理" })).toBeVisible();
    expect(screen.getByRole("button", { name: "验证服务" })).toBeVisible();
    expect(screen.queryByDisplayValue(/sk-/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "继续处理" }));
    expect(screen.getByRole("heading", { name: "连接信息" })).toBeVisible();
    expect(screen.getByLabelText("API 密钥")).toHaveValue("");
    expect(screen.getByRole("button", { name: "取消" })).toBeVisible();
  });

  test("模型服务低频操作收进更多菜单且已验证草稿发布入口可达", async () => {
    const user = userEvent.setup();
    const activeVersion = {
      id: "cfg-1",
      connection_id: "conn-1",
      version: 1,
      base_url: "https://api.example.com/v1",
      primary_model: "gpt-main",
      primary_effort: "medium",
      cheap_model: "gpt-cheap",
      cheap_effort: "low",
      secondary_model: "gpt-review",
      secondary_effort: "high",
      requests_per_minute: 60,
      max_workers: 4,
      timeout_seconds: 120,
      cheap_audit_percent: 5,
      validation_status: "validated",
      published_at: "2026-08-10T08:10:00Z",
    };
    const draftVersion = {
      ...activeVersion,
      id: "cfg-2",
      version: 2,
      change_note: "调整运行策略",
      published_at: null,
    };
    apiMock.configs.mockResolvedValue([
      {
        id: "conn-1",
        name: "生产模型服务",
        provider: "responses-compatible",
        active_version_id: "cfg-1",
        active_version: activeVersion,
        versions: [draftVersion, activeVersion],
        models: [],
      },
    ]);
    apiMock.publishConfig.mockResolvedValue(draftVersion);

    render(<ApiManagement notify={vi.fn()} />);

    expect(await screen.findByText("草稿 #2 · 可发布")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "发布版本" }));
    await waitFor(() => expect(apiMock.publishConfig).toHaveBeenCalledWith("cfg-2"));

    expect(
      screen.queryByRole("button", { name: "编辑模型策略" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("navigation", { name: "模型服务运维入口" }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "更多" }));
    await user.click(screen.getByRole("menuitem", { name: "请求限制" }));
    expect(screen.getByLabelText("每分钟请求")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "返回服务摘要" }));

    await user.click(screen.getByRole("button", { name: "更多" }));
    await user.click(screen.getByRole("menuitem", { name: "配置版本" }));
    expect(screen.getByRole("heading", { name: "配置版本" })).toBeVisible();

    await user.click(screen.getByRole("button", { name: "返回服务摘要" }));
    await user.click(screen.getByRole("button", { name: "更多" }));
    await user.click(screen.getByRole("menuitem", { name: "新增模型服务" }));
    expect(screen.getByRole("heading", { name: "新建模型服务" })).toBeVisible();
  });

  test("系统目标会选中配置版本并高亮指定模型", async () => {
    const scrollProbe = vi.spyOn(globalThis.HTMLElement.prototype, "scrollIntoView");
    const baseVersion = {
      connection_id: "conn-1",
      base_url: "https://api.example.com/v1",
      primary_model: "gpt-main",
      primary_effort: "medium",
      validation_status: "validated",
      creator_name: "管理员",
      created_at: "2026-08-12T08:00:00Z",
    };
    apiMock.configs.mockResolvedValue([
      {
        id: "conn-1",
        name: "生产线路",
        provider: "responses-compatible",
        active_version_id: "version-1",
        active_version: { ...baseVersion, id: "version-1", version: 1 },
        versions: [
          { ...baseVersion, id: "version-1", version: 1 },
          { ...baseVersion, id: "version-2", version: 2 },
        ],
        models: [
          {
            id: "model-1",
            model_key: "gpt-main",
            display_name: "主分析模型",
            supported_efforts: ["medium"],
            active: true,
            validation_status: "validated",
          },
        ],
      },
    ]);

    const { container } = render(
      <ApiManagement
        notify={vi.fn()}
        focusConnectionId="conn-1"
        focusConfigVersionId="version-2"
        focusModelId="model-1"
      />,
    );

    await waitFor(() =>
      expect(container.querySelector(".model-catalog-row.is-targeted")).toBeTruthy(),
    );
    expect(await screen.findByText(/配置 #2/)).toBeVisible();
    expect(scrollProbe).toHaveBeenCalled();
    scrollProbe.mockRestore();
  });

  test("用户目标会高亮并滚入对应成员", async () => {
    const scrollProbe = vi.spyOn(globalThis.HTMLElement.prototype, "scrollIntoView");
    apiMock.users.mockResolvedValue([
      {
        id: "user-1",
        display_name: "管理员",
        email: "admin@example.com",
        active: true,
      },
      {
        id: "user-2",
        display_name: "复核员",
        email: "review@example.com",
        active: true,
      },
    ]);

    render(
      <TeamPage
        notify={vi.fn()}
        currentUser={{ id: "user-1", display_name: "管理员" }}
        focusUserId="user-2"
      />,
    );

    const target = (await screen.findByText("复核员")).closest(".member-table > div");
    expect(target).toHaveClass("is-targeted");
    expect(target).toHaveAttribute("aria-current", "true");
    expect(scrollProbe).toHaveBeenCalled();
    scrollProbe.mockRestore();
  });

  test("移除历史任务焦点后回到进行中并选择首个可运行任务", async () => {
    const baseTask = {
      stage: "准备数据",
      message: "等待运行",
      revision: 1,
      progress_percent: 0,
      progress_current: 0,
      progress_total: 1,
      owner_name: "管理员",
      created_at: "2026-08-12T08:00:00Z",
      metrics: {},
      snapshot: {},
      segments: [],
      events: [],
    };
    const finishedTask = {
      ...baseTask,
      id: "task-finished-focus",
      title: "已取消历史任务",
      status: "cancelled",
      stage: "已取消（有部分结果）",
      result_file_path: "runtime/results/partial.xlsx",
    };
    const activeTask = {
      ...baseTask,
      id: "task-active",
      title: "当前运行任务",
      status: "running",
    };
    apiMock.tasks.mockResolvedValue([finishedTask, activeTask]);
    apiMock.task.mockImplementation((id) =>
      Promise.resolve(id === finishedTask.id ? finishedTask : activeTask),
    );
    const notify = vi.fn();
    const onNavigate = vi.fn();
    const onChanged = vi.fn();

    const { container, rerender } = render(
      <TaskMonitor
        notify={notify}
        onNavigate={onNavigate}
        onChanged={onChanged}
        focusId={finishedTask.id}
      />,
    );
    const detail = container.querySelector(".task-detail-panel");
    expect(await within(detail).findByText("已取消历史任务")).toBeVisible();
    expect(screen.getByRole("button", { name: "全部" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    rerender(
      <TaskMonitor
        notify={notify}
        onNavigate={onNavigate}
        onChanged={onChanged}
        focusId={null}
      />,
    );

    expect(await within(detail).findByText("当前运行任务")).toBeVisible();
    expect(screen.getByRole("button", { name: "进行中" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(within(detail).queryByText("已取消历史任务")).not.toBeInTheDocument();
  });

  test("移除历史任务焦点且没有进行中任务时清空详情", async () => {
    const finishedTask = {
      id: "task-only-finished",
      title: "唯一已取消任务",
      status: "cancelled",
      stage: "已取消（有部分结果）",
      message: "已保留部分结果",
      revision: 1,
      result_file_path: "runtime/results/partial.xlsx",
      progress_percent: 50,
      progress_current: 1,
      progress_total: 2,
      owner_name: "管理员",
      created_at: "2026-08-12T08:00:00Z",
      metrics: {},
      snapshot: {},
      segments: [],
      events: [],
    };
    apiMock.tasks.mockResolvedValue([finishedTask]);
    apiMock.task.mockResolvedValue(finishedTask);
    const notify = vi.fn();
    const onNavigate = vi.fn();
    const onChanged = vi.fn();

    const { container, rerender } = render(
      <TaskMonitor
        notify={notify}
        onNavigate={onNavigate}
        onChanged={onChanged}
        focusId={finishedTask.id}
      />,
    );
    const detail = container.querySelector(".task-detail-panel");
    expect(await within(detail).findByText("唯一已取消任务")).toBeVisible();

    rerender(
      <TaskMonitor
        notify={notify}
        onNavigate={onNavigate}
        onChanged={onChanged}
        focusId={null}
      />,
    );

    expect(await screen.findByText("暂无任务")).toBeVisible();
    expect(within(detail).getByText("选择一个任务")).toBeVisible();
    expect(within(detail).queryByText("唯一已取消任务")).not.toBeInTheDocument();
  });

  test("直接打开分析任务列表时不会默认展示已结束任务", async () => {
    const finishedTask = {
      id: "task-direct-finished",
      title: "不应默认展示的任务",
      status: "cancelled",
    };
    apiMock.tasks.mockResolvedValue([finishedTask]);

    const { container } = render(
      <TaskMonitor
        notify={vi.fn()}
        onNavigate={vi.fn()}
        onChanged={vi.fn()}
        focusId={null}
      />,
    );

    expect(await screen.findByText("暂无任务")).toBeVisible();
    expect(screen.getByRole("button", { name: "进行中" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(
      within(container.querySelector(".task-detail-panel")).getByText("选择一个任务"),
    ).toBeVisible();
    expect(apiMock.task).not.toHaveBeenCalled();
  });

  test("任务列表读取失败后显示错误并允许重新加载", async () => {
    const user = userEvent.setup();
    const notify = vi.fn();
    apiMock.tasks
      .mockRejectedValueOnce(new Error("任务服务暂不可用"))
      .mockResolvedValueOnce([]);

    const { container } = render(
      <TaskMonitor
        notify={notify}
        onNavigate={vi.fn()}
        onChanged={vi.fn()}
        focusId={null}
      />,
    );

    const error = await screen.findByRole("alert");
    expect(within(error).getByText("任务列表读取失败")).toBeVisible();
    expect(within(error).getByText("任务服务暂不可用")).toBeVisible();
    expect(screen.queryByText("读取任务…")).not.toBeInTheDocument();
    expect(container.querySelector(".task-detail-panel")).not.toBeInTheDocument();
    expect(notify).toHaveBeenCalledWith("任务服务暂不可用", "error");

    await user.click(screen.getByRole("button", { name: "重新加载" }));

    expect(await screen.findByText("暂无任务")).toBeVisible();
    expect(apiMock.tasks).toHaveBeenCalledTimes(2);
  });

  test("快速切换任务时旧详情响应不会覆盖新任务", async () => {
    let resolveOld;
    let resolveNew;
    const baseTask = {
      status: "queued",
      stage: "准备数据",
      message: "等待运行",
      revision: 1,
      progress_percent: 0,
      progress_current: 0,
      progress_total: 1,
      owner_name: "管理员",
      created_at: "2026-08-12T08:00:00Z",
      metrics: {},
      snapshot: {},
      segments: [],
      events: [],
    };
    const oldTask = { ...baseTask, id: "task-old", title: "旧任务详情" };
    const newTask = { ...baseTask, id: "task-new", title: "新任务详情" };
    apiMock.tasks.mockResolvedValue([oldTask, newTask]);
    apiMock.task.mockImplementation(
      (id) =>
        new Promise((resolve) => {
          if (id === "task-old") resolveOld = resolve;
          if (id === "task-new") resolveNew = resolve;
        }),
    );

    const { container, rerender } = render(
      <TaskMonitor
        notify={vi.fn()}
        onNavigate={vi.fn()}
        onChanged={vi.fn()}
        focusId="task-old"
      />,
    );
    await waitFor(() =>
      expect(apiMock.task).toHaveBeenCalledWith("task-old", expect.anything()),
    );

    rerender(
      <TaskMonitor
        notify={vi.fn()}
        onNavigate={vi.fn()}
        onChanged={vi.fn()}
        focusId="task-new"
      />,
    );
    await waitFor(() =>
      expect(apiMock.task).toHaveBeenCalledWith("task-new", expect.anything()),
    );
    await act(async () => resolveNew(newTask));

    const detail = container.querySelector(".task-detail-panel");
    expect(within(detail).getByText("新任务详情")).toBeVisible();

    await act(async () => resolveOld(oldTask));
    expect(within(detail).getByText("新任务详情")).toBeVisible();
    expect(within(detail).queryByText("旧任务详情")).not.toBeInTheDocument();
  });
});
