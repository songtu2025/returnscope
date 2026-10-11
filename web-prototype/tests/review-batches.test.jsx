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
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const { reviewBatchApiMock } = vi.hoisted(() => ({
  reviewBatchApiMock: {
    reviewBatches: vi.fn(),
    reviewBatch: vi.fn(),
    reviewBatchRecords: vi.fn(),
    updateReviewBatchRecord: vi.fn(),
    updateReviewBatchRecords: vi.fn(),
    publishReviewBatch: vi.fn(),
    reviewTaxonomy: vi.fn(),
  },
}));

vi.mock("../src/shared/api/reviewBatchApi", () => ({
  reviewBatchApi: reviewBatchApiMock,
}));

import { ReviewBatchPage } from "../src/features/review-batches/ReviewBatchPage";
import { ReviewBatchList } from "../src/features/review-batches/ReviewBatchList";
import { reviewBatchRouteState } from "../src/features/review-batches/reviewBatchRoute";

async function selectOption(label, option) {
  const combobox = screen.getByRole("combobox", { name: label });
  fireEvent.mouseDown(
    combobox.closest(".ant-select").querySelector(".ant-select-content"),
  );
  await userEvent.click(
    await screen.findByText(option, {
      selector: ".ant-select-item-option-content",
    }),
  );
  await waitFor(() => expect(combobox).toHaveAttribute("aria-expanded", "false"));
}

const baseBatch = {
  id: "review-batch-1",
  base_result_version_id: "classification-version-1",
  result_id: "classification-result-1",
  status: "draft",
  revision: 2,
  created_by: "user-1",
  created_at: "2026-08-12T08:00:00Z",
  updated_at: "2026-08-12T09:00:00Z",
  published_version_id: null,
  version_no: 1,
  base_version_no: 1,
  quality_status: "review_required",
  base_quality_status: "review_required",
  unit_count: 2,
  base_unit_count: 2,
  base_record_count: 3,
  store_site: "SEEKWAY:US",
  listing: "SR001",
  creator_name: "复核员甲",
  creator: { id: "user-1", display_name: "复核员甲" },
  record_count: 2,
  resolved_count: 0,
  excluded_count: 0,
  remaining_count: 2,
  derived_result_version_id: null,
  derived_version_no: null,
  derived_quality_status: null,
  derived_published_at: null,
};

const baseRecord = {
  id: "review-record-1",
  task_id: "task-1",
  batch_id: "review-batch-1",
  base_result_version_id: "classification-version-1",
  classification_key: "classification-key-1",
  comment: "Too small for me",
  workflow_status: "pending",
  revision: 1,
  updated_at: "2026-08-12T09:00:00Z",
  classification: {
    primary_label_codes: ["FIT_TOO_SMALL"],
    problem_label_codes: ["FIT_TOO_SMALL"],
    semantic_units: [
      { label_code: "FIT_TOO_SMALL", evidence: "Too small", opinion: "偏小" },
    ],
  },
  order_ids: ["ORDER-001", "ORDER-002"],
  product_names: ["产品表名称"],
  listings: ["SR001"],
  source_skus: ["SOURCE-MSKU-1"],
  matched_mskus: ["SOURCE-MSKU-1"],
  product_skus: ["PRODUCT-SKU-1"],
  record_count: 2,
};

function page(batch = baseBatch, records = [baseRecord]) {
  reviewBatchApiMock.reviewBatch.mockResolvedValue(batch);
  reviewBatchApiMock.reviewBatchRecords.mockResolvedValue({
    items: records,
    total: records.length,
    page: 1,
    page_size: 20,
  });
  return (
    <ReviewBatchPage
      route={{
        query: {
          review_batch_id: batch.id,
          result_version_id: batch.base_result_version_id,
        },
      }}
      notify={vi.fn()}
    />
  );
}

beforeEach(() => {
  window.location.hash = "classification-results?view=reviews";
  Object.values(reviewBatchApiMock).forEach((mock) => mock.mockReset());
  reviewBatchApiMock.reviewTaxonomy.mockResolvedValue({
    labels: [
      { code: "FIT_TOO_SMALL", name: "偏小", allowed_sentiments: ["NEGATIVE"] },
      { code: "FIT_TOO_LARGE", name: "偏大", allowed_sentiments: ["NEGATIVE"] },
    ],
  });
});

afterEach(() => cleanup());

test("复核批次详情等待时保留返回入口与页面占位", async () => {
  let resolveBatch;
  reviewBatchApiMock.reviewBatch.mockReturnValue(
    new Promise((resolve) => {
      resolveBatch = resolve;
    }),
  );
  reviewBatchApiMock.reviewBatchRecords.mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
  });

  render(
    <ReviewBatchPage
      route={{ query: { review_batch_id: baseBatch.id } }}
      notify={vi.fn()}
    />,
  );

  expect(await screen.findByText("正在读取历史复核记录…")).toBeVisible();
  expect(screen.getByRole("button", { name: "返回历史复核记录" })).toBeVisible();
  expect(
    screen.getByText("正在读取历史复核记录…").closest(".standard-page"),
  ).toBeInTheDocument();

  await act(async () => resolveBatch(baseBatch));
  expect(screen.queryByText("正在读取历史复核记录…")).not.toBeInTheDocument();
});

test("批次列表从 URL 恢复服务端筛选并查看历史", async () => {
  reviewBatchApiMock.reviewBatches.mockResolvedValue({
    items: [baseBatch],
    total: 21,
    page: 2,
    page_size: 20,
  });
  render(
    <ReviewBatchPage
      route={{ query: { status: "draft", q: "SR001", page: "2" } }}
      notify={vi.fn()}
    />,
  );

  expect(await screen.findByText("复核员甲")).toBeVisible();
  const filters = screen.getByRole("region", { name: "复核批次筛选" });
  for (const label of ["关键词", "批次状态"]) {
    expect(within(filters).getByText(label, { selector: "span" })).toBeVisible();
  }
  expect(screen.getByRole("button", { name: "返回分类结果池" })).toBeVisible();
  expect(screen.queryByRole("button", { name: "复核记录" })).toBeNull();
  expect(reviewBatchApiMock.reviewBatches).toHaveBeenCalledWith(
    {
      page: 2,
      page_size: 20,
      status: "draft",
      base_result_version_id: "",
      q: "SR001",
    },
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
  );
  await userEvent.click(screen.getByRole("button", { name: /查看历史/ }));
  expect(window.location.hash).toContain("review_batch_id=review-batch-1");
  expect(window.location.hash).toContain("result_version_id=classification-version-1");
});

test("编辑批次筛选草稿不提前请求，确认筛选才更新路由", async () => {
  reviewBatchApiMock.reviewBatches.mockResolvedValue({ items: [baseBatch], total: 1 });
  const updateRoute = vi.fn();
  render(
    <ReviewBatchList
      route={reviewBatchRouteState({ q: "SR001", status: "draft", page: "3" })}
      updateRoute={updateRoute}
    />,
  );
  await screen.findByText("复核员甲");

  await userEvent.clear(screen.getByRole("textbox", { name: "搜索复核批次" }));
  await userEvent.type(
    screen.getByRole("textbox", { name: "搜索复核批次" }),
    "新关键词",
  );
  await selectOption("批次状态", "已发布");
  expect(reviewBatchApiMock.reviewBatches).toHaveBeenCalledTimes(1);
  expect(updateRoute).not.toHaveBeenCalled();

  await userEvent.click(screen.getByRole("button", { name: "筛选", exact: true }));
  expect(updateRoute).toHaveBeenCalledExactlyOnceWith({
    q: "新关键词",
    status: "published",
    page: 1,
  });
});

test("查看历史只重置原有记录筛选，保留分页大小与返回上下文", async () => {
  reviewBatchApiMock.reviewBatches.mockResolvedValue({ items: [baseBatch], total: 1 });
  const updateRoute = vi.fn();
  render(
    <ReviewBatchList
      route={reviewBatchRouteState({
        q: "SR001",
        status: "draft",
        page: "3",
        page_size: "50",
        task_id: "task-1",
        segment_id: "segment-1",
        return_to: "workbench",
      })}
      updateRoute={updateRoute}
    />,
  );
  await userEvent.click(await screen.findByRole("button", { name: /查看历史/ }));
  expect(updateRoute).toHaveBeenCalledExactlyOnceWith({
    batchId: baseBatch.id,
    resultVersionId: baseBatch.base_result_version_id,
    status: "",
    page: 1,
    listing: "",
    productName: "",
    productSku: "",
    orderId: "",
    q: "",
  });
});

test("批次查询变化会取消旧请求，迟到的旧响应不覆盖新列表", async () => {
  let finishOld;
  reviewBatchApiMock.reviewBatches
    .mockReturnValueOnce(
      new Promise((resolve) => {
        finishOld = resolve;
      }),
    )
    .mockResolvedValueOnce({
      items: [{ ...baseBatch, creator_name: "新列表创建人" }],
      total: 1,
    });
  const updateRoute = vi.fn();
  const { rerender } = render(
    <ReviewBatchList
      route={reviewBatchRouteState({ q: "旧查询" })}
      updateRoute={updateRoute}
    />,
  );
  await waitFor(() =>
    expect(reviewBatchApiMock.reviewBatches).toHaveBeenCalledTimes(1),
  );
  const oldSignal = reviewBatchApiMock.reviewBatches.mock.calls[0][1].signal;
  rerender(
    <ReviewBatchList
      route={reviewBatchRouteState({ q: "新查询" })}
      updateRoute={updateRoute}
    />,
  );
  expect(await screen.findByText("新列表创建人")).toBeVisible();
  expect(oldSignal.aborted).toBe(true);
  await act(async () => finishOld({ items: [baseBatch], total: 1 }));
  expect(screen.getByText("新列表创建人")).toBeVisible();
  expect(screen.queryByText("复核员甲")).not.toBeInTheDocument();
  expect(reviewBatchApiMock.reviewBatches).toHaveBeenCalledTimes(2);
});

test("空复核记录引导用户查看待复核分类结果", async () => {
  reviewBatchApiMock.reviewBatches.mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
  });
  const user = userEvent.setup();
  render(<ReviewBatchPage route={{ query: {} }} notify={vi.fn()} />);

  await user.click(await screen.findByRole("button", { name: /查看分类结果/ }));

  expect(window.location.hash).toBe(
    "#classification-results?quality_status=review_required",
  );
});

test("新版复核接口 404 使用友好文案并折叠技术错误", async () => {
  const notFound = Object.assign(new Error("Not Found"), { status: 404 });
  reviewBatchApiMock.reviewBatches.mockRejectedValue(notFound);

  render(<ReviewBatchPage route={{ query: {} }} notify={vi.fn()} />);

  expect(await screen.findByText("新版复核服务尚不可用，请稍后重新加载")).toBeVisible();
  expect(screen.getByText("查看技术详情")).toBeVisible();
  await userEvent.click(screen.getByText("查看技术详情"));
  expect(screen.getByText("Not Found")).toBeVisible();
});

test("待处理批次展示真实业务字段并阻止提前发布", async () => {
  render(page());

  expect(await screen.findByText("产品表名称")).toBeVisible();
  expect(screen.getByText("ORDER-001、ORDER-002")).toBeVisible();
  expect(screen.getByText("产品SKU：PRODUCT-SKU-1")).toBeVisible();
  expect(screen.getByText("匹配MSKU：SOURCE-MSKU-1")).toBeVisible();
  const filters = screen.getByRole("region", { name: "复核记录筛选" });
  for (const label of [
    "关键词",
    "处理状态",
    "Listing",
    "产品名称",
    "产品 SKU",
    "order-id",
  ]) {
    expect(within(filters).getByText(label, { selector: "span" })).toBeVisible();
  }
  expect(
    within(filters).getByRole("button", { name: "筛选", exact: true }),
  ).toBeVisible();
  expect(screen.queryByText("鞋履")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "还剩 2 条需处理" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "发布派生版本" }),
  ).not.toBeInTheDocument();
  expect(reviewBatchApiMock.updateReviewBatchRecord).not.toHaveBeenCalled();

  await userEvent.click(screen.getByRole("button", { name: "查看" }));
  const drawer = screen.getByRole("dialog", { name: "ORDER-001、ORDER-002" });
  expect(within(drawer).getByText("产品表名称")).toBeVisible();
  expect(within(drawer).getByText("PRODUCT-SKU-1")).toBeVisible();
  expect(within(drawer).getAllByText("SOURCE-MSKU-1")).toHaveLength(2);
});

test("复核记录摘要展示完整问题和正向标签而非主因标签", async () => {
  const semanticRecord = {
    ...baseRecord,
    problem_label_paths: {
      FIT_TOO_SMALL: ["尺寸", "偏小"],
      FIT_TOO_LARGE: ["尺寸", "偏大"],
      WARM: ["体验", "保暖良好"],
    },
    classification: {
      ...baseRecord.classification,
      primary_label_codes: ["FIT_TOO_SMALL"],
      problem_label_codes: ["FIT_TOO_LARGE"],
      positive_label_codes: ["WARM"],
    },
  };

  render(page(baseBatch, [semanticRecord]));

  expect(await screen.findByText("尺寸 → 偏大、体验 → 保暖良好")).toBeVisible();
  expect(screen.queryByText("尺寸 → 偏小")).not.toBeInTheDocument();
});

test("复核抽屉限制键盘焦点并在关闭后恢复触发按钮", async () => {
  render(page());
  const trigger = await screen.findByRole("button", { name: "查看" });
  await userEvent.click(trigger);
  const drawer = screen.getByRole("dialog", { name: "ORDER-001、ORDER-002" });
  const close = within(drawer).getByRole("button", { name: "关闭复核抽屉" });
  expect(close).toHaveFocus();
  await userEvent.tab({ shift: true });
  expect(
    within(drawer).getByText("查看完整语义详情", { selector: "summary" }),
  ).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});

test("产品快照字段缺失时明确显示未提供且不用品类兜底", async () => {
  render(
    page(baseBatch, [
      {
        ...baseRecord,
        product_names: [],
        product_skus: [],
        category_a: "鞋履",
        category_b: "儿童水鞋",
      },
    ]),
  );

  expect(await screen.findAllByText("未提供")).not.toHaveLength(0);
  expect(screen.queryByText("鞋履")).not.toBeInTheDocument();
  expect(screen.queryByText("儿童水鞋")).not.toBeInTheDocument();
});

test("语义核验清单逐项展示并将系统异常置顶且锁定编辑", async () => {
  const semanticRecord = {
    ...baseRecord,
    comment: "Warm, but the fingers are too long.",
    classification: {
      ...baseRecord.classification,
      semantic_review: {
        semantic_items: [
          {
            item_id: "mapped-1",
            evidence_text: "Warm",
            opinion: "保暖效果好",
            label_code: "FIT_TOO_SMALL",
            disposition: "MAPPED",
          },
          {
            item_id: "ignored-1",
            evidence_text: "for winter",
            opinion: "使用季节信息",
            disposition: "NO_TAG_NEEDED",
          },
          {
            item_id: "failed-1",
            evidence_text: "fingers are too long",
            opinion: "系统未完成分析",
            disposition: "ANALYSIS_FAILURE",
            reason: "模型响应失败",
            diagnostic_domain: "TECHNICAL_RUNTIME",
            diagnostic_code: "SECONDARY_MODEL_TIMEOUT",
            diagnostic_title: "风险复核调用超时",
            detail_status: "AVAILABLE",
            primary_result: "首次分析：手指过长",
            secondary_result: "风险复核：未返回",
            detail: "风险复核模型在时限内未返回结果",
            action: "请系统重试风险复核。",
          },
          {
            item_id: "unknown-1",
            evidence_text: "too long",
            opinion: "指长问题待判断",
            disposition: "TRUE_AMBIGUITY",
          },
        ],
        coverage_summary: {
          mapped: 1,
          no_tag_needed: 1,
          true_ambiguity: 1,
          taxonomy_gap: 0,
          analysis_failure: 1,
          unexplained_fragment_count: 1,
        },
        unexplained_fragments: ["but"],
      },
    },
  };
  render(page(baseBatch, [semanticRecord]));

  await userEvent.click(await screen.findByRole("button", { name: "查看" }));
  const ledger = screen.getByRole("region", { name: "语义核验清单" });
  expect(within(ledger).getByText("无需归类 1")).toBeVisible();
  expect(within(ledger).getByText("待判断 2")).toBeVisible();
  expect(within(ledger).getByText("系统异常 1")).toBeVisible();
  const systemGroup = within(ledger).getByRole("region", { name: "系统异常" });
  const businessGroup = within(ledger).getByRole("region", {
    name: "待人工判断",
  });
  expect(within(systemGroup).getByText("系统异常 · 1 项")).toBeVisible();
  expect(within(systemGroup).getByText("历史记录")).toBeVisible();
  expect(within(businessGroup).getByText("待人工判断 · 2 项")).toBeVisible();
  const items = within(ledger).getAllByRole("article");
  expect(within(items[0]).getByText("系统处理失败")).toBeVisible();
  expect(within(items[0]).getByText("风险复核调用超时")).toBeVisible();
  expect(
    within(items[0]).getByText(/运行异常 · SECONDARY_MODEL_TIMEOUT/),
  ).toBeVisible();
  expect(within(items[0]).getByText("首次分析：手指过长")).toBeVisible();
  expect(within(items[0]).getByText("风险复核：未返回")).toBeVisible();
  expect(within(items[0]).getByText("风险复核模型在时限内未返回结果")).toBeVisible();
  expect(within(items[0]).getByText("请系统重试风险复核。")).toBeVisible();
  for (const label of ["首次结果", "复核结果", "差异说明", "处理建议"]) {
    expect(within(items[0]).getByText(label)).toBeVisible();
  }
  expect(within(items[0]).queryByRole("button", { name: "调整" })).toBeNull();
  expect(within(items[1]).getByText("原文含义不明确")).toBeVisible();
  expect(within(items[2]).getByText("未解释原文片段")).toBeVisible();
  expect(within(items[2]).getByText(/but/)).toBeVisible();
  expect(within(items[3]).getByText("保暖效果好")).toBeVisible();
  expect(screen.getByText("展开完整原文上下文")).toBeVisible();
  expect(screen.getByText("查看完整语义详情")).toBeVisible();
});

test("已处理记录展示分别保存的复核质量判断", async () => {
  const resolvedRecord = {
    ...baseRecord,
    workflow_status: "resolved",
    classification: {
      ...baseRecord.classification,
      human_review_assessment: {
        label_correctness: "incorrect",
        evidence_completeness: "partial",
        review_routing: "should_manual_review",
        assessed_by: "user-1",
        assessed_at: "2026-08-12T10:00:00Z",
      },
    },
  };
  render(page(baseBatch, [resolvedRecord]));

  await userEvent.click(await screen.findByRole("button", { name: "查看" }));
  const summary = screen.getByRole("region", { name: "已保存的复核质量判断" });
  expect(within(summary).getByText("错误")).toBeVisible();
  expect(within(summary).getByText("部分完整")).toBeVisible();
  expect(within(summary).getByText("本应人工复核")).toBeVisible();
});

test("已发布批次只读且显示实际派生版本", async () => {
  const published = {
    ...baseBatch,
    status: "published",
    resolved_count: 2,
    remaining_count: 0,
    derived_result_version_id: "classification-version-2",
    derived_version_no: 2,
  };
  render(page(published, [{ ...baseRecord, workflow_status: "resolved" }]));

  expect(await screen.findByText(/历史批次仅供查看/)).toBeVisible();
  expect(screen.getByRole("button", { name: /查看衍生版本/ })).toBeEnabled();
  expect(
    screen.queryByRole("button", { name: /创建分析看板/ }),
  ).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "查看" }));
  expect(screen.queryByText("复核结论")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "仅保存" })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /查看衍生版本/ }));
  expect(window.location.hash).toContain("result_version_id=classification-version-2");
  expect(window.location.hash).toContain("review_batch_id=review-batch-1");
});

test("快速切换批次时旧请求不会覆盖新批次", async () => {
  let resolveOld;
  let oldSignal;
  const newBatch = { ...baseBatch, id: "review-batch-2", listing: "NEW001" };
  reviewBatchApiMock.reviewBatch.mockImplementation((id, options) => {
    if (id === "review-batch-1") {
      oldSignal = options.signal;
      return new Promise((resolve) => {
        resolveOld = resolve;
      });
    }
    return Promise.resolve(newBatch);
  });
  reviewBatchApiMock.reviewBatchRecords.mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
  });
  const { rerender } = render(
    <ReviewBatchPage
      route={{ query: { review_batch_id: "review-batch-1" } }}
      notify={vi.fn()}
    />,
  );
  await waitFor(() => expect(oldSignal).toBeInstanceOf(AbortSignal));

  rerender(
    <ReviewBatchPage
      route={{ query: { review_batch_id: "review-batch-2" } }}
      notify={vi.fn()}
    />,
  );
  expect(await screen.findByText("NEW001 复核批次")).toBeVisible();
  expect(oldSignal.aborted).toBe(true);

  await act(async () => resolveOld(baseBatch));
  expect(screen.getByText("NEW001 复核批次")).toBeVisible();
  expect(screen.queryByText("SR001 复核批次")).not.toBeInTheDocument();
});

test("批次更新失败保留上次列表，重试恢复且权限失效清除数据", async () => {
  reviewBatchApiMock.reviewBatches
    .mockResolvedValueOnce({ items: [baseBatch], total: 1 })
    .mockRejectedValueOnce(new Error("连接中断"))
    .mockRejectedValueOnce(Object.assign(new Error("无权访问"), { status: 403 }))
    .mockResolvedValueOnce({ items: [baseBatch], total: 1 });
  const updateRoute = vi.fn();
  const { rerender } = render(
    <ReviewBatchList route={reviewBatchRouteState({})} updateRoute={updateRoute} />,
  );
  await screen.findByText("复核员甲");
  rerender(
    <ReviewBatchList
      route={reviewBatchRouteState({ q: "更新" })}
      updateRoute={updateRoute}
    />,
  );
  await screen.findByText("复核批次更新失败，当前显示上一次数据");
  expect(screen.getByText("复核员甲")).toBeVisible();
  expect(screen.getByRole("table", { name: "复核批次" })).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "重新加载" }));
  await screen.findByText("无权访问");
  expect(screen.queryByText("复核员甲")).not.toBeInTheDocument();
  expect(screen.queryByText("没有符合条件的复核批次")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "重新加载" }));
  await screen.findByText("复核员甲");
});

test("批次筛选为空提供清除筛选且保留来源版本", async () => {
  reviewBatchApiMock.reviewBatches.mockResolvedValue({ items: [], total: 0 });
  const updateRoute = vi.fn();
  render(
    <ReviewBatchList
      route={reviewBatchRouteState({ q: "无结果", status: "draft" })}
      updateRoute={updateRoute}
    />,
  );
  await screen.findByText("没有符合条件的复核批次");
  await userEvent.click(screen.getByRole("button", { name: "清除筛选" }));
  expect(updateRoute).toHaveBeenCalledWith({ q: "", status: "", page: 1 });
});
