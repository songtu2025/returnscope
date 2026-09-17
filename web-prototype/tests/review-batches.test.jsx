import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
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
      { code: "FIT_TOO_SMALL", name: "偏小" },
      { code: "FIT_TOO_LARGE", name: "偏大" },
    ],
  });
});

afterEach(() => cleanup());

test("批次列表从 URL 恢复服务端筛选并进入批次", async () => {
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
  expect(screen.getByRole("button", { name: "复核记录" })).toHaveAttribute(
    "aria-current",
    "page",
  );
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
  await userEvent.click(screen.getByRole("button", { name: /进入批次/ }));
  expect(window.location.hash).toContain("review_batch_id=review-batch-1");
  expect(window.location.hash).toContain("result_version_id=classification-version-1");
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

  await user.click(await screen.findByRole("button", { name: /查看待复核结果/ }));

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
  expect(screen.queryByText("鞋履")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "还剩 2 条需处理" })).toBeDisabled();

  await userEvent.click(screen.getByRole("button", { name: "处理" }));
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

test("修改分类时不使用主因作为预选标签", async () => {
  const semanticRecord = {
    ...baseRecord,
    classification: {
      ...baseRecord.classification,
      primary_label_codes: ["FIT_TOO_SMALL"],
      problem_label_codes: ["FIT_TOO_LARGE"],
      positive_label_codes: ["WARM"],
    },
  };

  render(page(baseBatch, [semanticRecord]));

  await userEvent.click(await screen.findByRole("button", { name: "处理" }));
  await userEvent.click(screen.getByRole("button", { name: /修改分类/ }));
  expect(screen.getByLabelText("修改分类标签")).toHaveValue("FIT_TOO_LARGE");
});

test("待处理记录回填已存在的复核质量判断", async () => {
  const assessedRecord = {
    ...baseRecord,
    classification: {
      ...baseRecord.classification,
      human_review_assessment: {
        label_correctness: "incorrect",
        evidence_completeness: "partial",
        review_routing: "should_auto_approve",
      },
    },
  };
  render(page(baseBatch, [assessedRecord]));

  await userEvent.click(await screen.findByRole("button", { name: "处理" }));
  expect(screen.getByLabelText("标签正确性")).toHaveValue("incorrect");
  expect(screen.getByLabelText("证据完整性")).toHaveValue("partial");
  expect(screen.getByLabelText("路由合理性")).toHaveValue("should_auto_approve");
});

test("复核抽屉限制键盘焦点并在关闭后恢复触发按钮", async () => {
  render(page());
  const trigger = await screen.findByRole("button", { name: "处理" });
  await userEvent.click(trigger);
  const drawer = screen.getByRole("dialog", { name: "ORDER-001、ORDER-002" });
  const close = within(drawer).getByRole("button", { name: "关闭复核抽屉" });
  expect(close).toHaveFocus();
  await userEvent.tab({ shift: true });
  expect(
    within(drawer).getByPlaceholderText("必填：说明确认、修改或排除的判断依据"),
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

test("确认原结果同时提交标签、证据和路由质量判断", async () => {
  reviewBatchApiMock.updateReviewBatchRecord.mockResolvedValue({
    id: baseRecord.id,
    workflow_status: "resolved",
    revision: 2,
  });
  const resolvedRecord = {
    ...baseRecord,
    workflow_status: "resolved",
    revision: 2,
  };
  const view = page();
  reviewBatchApiMock.reviewBatchRecords
    .mockResolvedValueOnce({ items: [baseRecord], total: 1, page: 1, page_size: 20 })
    .mockResolvedValue({ items: [resolvedRecord], total: 1, page: 1, page_size: 20 });
  render(view);

  await userEvent.click(await screen.findByRole("button", { name: "处理" }));
  expect(screen.getByLabelText("标签正确性")).toHaveValue("correct");
  expect(screen.getByLabelText("证据完整性")).toHaveValue("complete");
  expect(screen.getByLabelText("路由合理性")).toHaveValue("correct");
  await userEvent.selectOptions(screen.getByLabelText("标签正确性"), "partial");
  await userEvent.selectOptions(screen.getByLabelText("证据完整性"), "missing");
  await userEvent.selectOptions(
    screen.getByLabelText("路由合理性"),
    "should_auto_approve",
  );
  await userEvent.type(
    screen.getByPlaceholderText("必填：说明确认、修改或排除的判断依据"),
    "证据与原标签一致",
  );
  await userEvent.click(screen.getByRole("button", { name: "仅保存" }));

  await waitFor(() =>
    expect(reviewBatchApiMock.updateReviewBatchRecord).toHaveBeenCalledWith(
      "review-batch-1",
      "review-record-1",
      {
        expected_revision: 1,
        action: "confirm",
        label_code: null,
        reason: "证据与原标签一致",
        label_correctness: "partial",
        evidence_completeness: "missing",
        review_routing: "should_auto_approve",
        semantic_item_reviews: [],
        added_semantic_items: [],
        coverage_status: "complete",
      },
    ),
  );
  const drawer = await screen.findByRole("dialog", {
    name: "ORDER-001、ORDER-002",
  });
  expect(within(drawer).getByText("产品表名称")).toBeVisible();
  expect(within(drawer).getByText("PRODUCT-SKU-1")).toBeVisible();
  expect(within(drawer).getByText("2")).toBeVisible();
});

test("语义核验清单按证据观点和处置展示，并将异常置顶", async () => {
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
            business_review_required: false,
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

  await userEvent.click(await screen.findByRole("button", { name: "处理" }));
  const ledger = screen.getByRole("region", { name: "语义核验清单" });
  expect(within(ledger).getByText("无需归类 1")).toBeVisible();
  expect(within(ledger).getByText("待判断 2")).toBeVisible();
  expect(within(ledger).getByText("系统异常 1")).toBeVisible();
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
  expect(within(items[0]).queryByRole("button", { name: "调整" })).toBeNull();
  expect(within(items[1]).getByText("原文含义不明确")).toBeVisible();
  expect(within(items[2]).getByText("未解释原文片段")).toBeVisible();
  expect(within(items[2]).getByText(/but/)).toBeVisible();
  expect(within(items[3]).getByText("保暖效果好")).toBeVisible();
  expect(screen.getByText("展开完整原文上下文")).toBeVisible();
  expect(screen.getByText("查看完整语义详情")).toBeVisible();
});

test("逐项调整和补充遗漏观点随整条确认提交", async () => {
  reviewBatchApiMock.updateReviewBatchRecord.mockResolvedValue({
    ...baseRecord,
    workflow_status: "resolved",
    revision: 2,
  });
  render(page(baseBatch, [baseRecord]));

  await userEvent.click(await screen.findByRole("button", { name: "处理" }));
  await userEvent.click(screen.getByRole("button", { name: "调整" }));
  await userEvent.selectOptions(
    screen.getByLabelText("调整方式：偏小"),
    "no_tag_needed",
  );
  await userEvent.click(screen.getByRole("button", { name: "保存本项调整" }));
  await userEvent.selectOptions(screen.getByLabelText("观点覆盖判断"), "has_omission");
  await userEvent.click(screen.getByRole("button", { name: "补充遗漏观点" }));
  await userEvent.type(
    screen.getByPlaceholderText("粘贴能够支持该观点的原文片段"),
    "for me",
  );
  await userEvent.type(
    screen.getByPlaceholderText("用一句话概括用户表达的观点"),
    "个人尺寸体验",
  );
  await userEvent.selectOptions(
    screen.getByLabelText("补充观点的归类标签"),
    "FIT_TOO_LARGE",
  );
  await userEvent.click(screen.getByRole("button", { name: "添加观点" }));
  await userEvent.type(
    screen.getByPlaceholderText("必填：说明确认、修改或排除的判断依据"),
    "按原文补充和调整",
  );
  await userEvent.click(screen.getByRole("button", { name: "仅保存" }));

  await waitFor(() =>
    expect(reviewBatchApiMock.updateReviewBatchRecord).toHaveBeenCalledWith(
      "review-batch-1",
      "review-record-1",
      expect.objectContaining({
        semantic_item_reviews: [
          {
            semantic_item_id: "semantic-item-0",
            action: "no_tag_needed",
            label_code: null,
            note: null,
          },
        ],
        added_semantic_items: [
          {
            item_id: "manual-1",
            evidence_text: "for me",
            opinion: "个人尺寸体验",
            label_code: "FIT_TOO_LARGE",
            note: "人工补充的遗漏观点",
          },
        ],
        coverage_status: "has_omission",
      }),
    ),
  );
});

test("可选择本页待处理记录并批量排除", async () => {
  const secondRecord = {
    ...baseRecord,
    id: "review-record-2",
    classification_key: "classification-key-2",
    order_ids: ["ORDER-003"],
  };
  reviewBatchApiMock.updateReviewBatchRecords.mockResolvedValue({
    updated_count: 2,
    batch: { ...baseBatch, revision: 3, excluded_count: 2, remaining_count: 0 },
  });
  render(page(baseBatch, [baseRecord, secondRecord]));

  await userEvent.click(
    await screen.findByRole("checkbox", { name: "选择本页待处理记录" }),
  );
  await userEvent.click(screen.getByRole("button", { name: /批量排除/ }));
  expect(screen.getByText(/仍保留原始记录和操作记录/)).toBeVisible();
  await userEvent.type(
    screen.getByPlaceholderText("必填：说明本次批量处理的判断依据"),
    "不属于有效产品反馈",
  );
  await userEvent.click(screen.getByRole("button", { name: "确认处理 2 条" }));

  await waitFor(() =>
    expect(reviewBatchApiMock.updateReviewBatchRecords).toHaveBeenCalledWith(
      "review-batch-1",
      {
        records: [
          { id: "review-record-1", expected_revision: 1 },
          { id: "review-record-2", expected_revision: 1 },
        ],
        action: "exclude",
        label_code: null,
        reason: "不属于有效产品反馈",
      },
    ),
  );
});

test("单条处理后可直接进入下一条待处理记录", async () => {
  const secondRecord = {
    ...baseRecord,
    id: "review-record-2",
    classification_key: "classification-key-2",
    order_ids: ["ORDER-003"],
  };
  reviewBatchApiMock.updateReviewBatchRecord.mockResolvedValue({
    ...baseRecord,
    workflow_status: "resolved",
    revision: 2,
  });
  render(page(baseBatch, [baseRecord, secondRecord]));

  await userEvent.click((await screen.findAllByRole("button", { name: "处理" }))[0]);
  await userEvent.type(
    screen.getByPlaceholderText("必填：说明确认、修改或排除的判断依据"),
    "证据一致",
  );
  await userEvent.click(screen.getByRole("button", { name: "保存并下一条" }));

  expect(await screen.findByRole("dialog", { name: "ORDER-003" })).toBeVisible();
});

test("单条 409 保留我的输入并可基于服务器新 revision 重试", async () => {
  const conflict = Object.assign(new Error("记录已被其他用户修改，请刷新后重试"), {
    status: 409,
  });
  const latestBatch = { ...baseBatch, revision: 3 };
  const latestRecord = { ...baseRecord, revision: 2 };
  reviewBatchApiMock.reviewBatch
    .mockResolvedValueOnce(baseBatch)
    .mockResolvedValue(latestBatch);
  reviewBatchApiMock.reviewBatchRecords
    .mockResolvedValueOnce({ items: [baseRecord], total: 1, page: 1, page_size: 20 })
    .mockResolvedValue({ items: [latestRecord], total: 1, page: 1, page_size: 20 });
  reviewBatchApiMock.updateReviewBatchRecord
    .mockRejectedValueOnce(conflict)
    .mockResolvedValue({
      ...latestRecord,
      workflow_status: "resolved",
      revision: 3,
    });

  render(
    <ReviewBatchPage
      route={{ query: { review_batch_id: "review-batch-1" } }}
      notify={vi.fn()}
    />,
  );
  await userEvent.click(await screen.findByRole("button", { name: "处理" }));
  await userEvent.click(screen.getByRole("button", { name: /修改分类/ }));
  expect(screen.getByLabelText("标签正确性")).toHaveValue("partial");
  expect(screen.getByLabelText("证据完整性")).toHaveValue("partial");
  expect(screen.getByLabelText("路由合理性")).toHaveValue("should_manual_review");
  await userEvent.selectOptions(screen.getByLabelText("修改分类标签"), "FIT_TOO_LARGE");
  const reason = screen.getByPlaceholderText("必填：说明确认、修改或排除的判断依据");
  await userEvent.type(reason, "实物证据指向偏大");
  await userEvent.click(screen.getByRole("button", { name: "仅保存" }));

  expect(await screen.findByText("服务器最新")).toBeVisible();
  expect(screen.getByText("修订 #2")).toBeVisible();
  expect(screen.getByText("我的未保存")).toBeVisible();
  expect(screen.getAllByText("实物证据指向偏大")).toHaveLength(2);
  expect(reason).toHaveValue("实物证据指向偏大");

  await userEvent.click(screen.getByRole("button", { name: "基于新修订继续编辑" }));
  expect(reason).toHaveValue("实物证据指向偏大");
  await userEvent.click(screen.getByRole("button", { name: "仅保存" }));
  await waitFor(() =>
    expect(reviewBatchApiMock.updateReviewBatchRecord).toHaveBeenLastCalledWith(
      "review-batch-1",
      "review-record-1",
      expect.objectContaining({ expected_revision: 2, reason: "实物证据指向偏大" }),
    ),
  );
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

test("发布 409 留在弹窗刷新 revision，确认后进入派生版本历史", async () => {
  const completed = {
    ...baseBatch,
    revision: 4,
    resolved_count: 2,
    remaining_count: 0,
  };
  const refreshed = { ...completed, revision: 5 };
  const conflict = Object.assign(new Error("批次已被其他用户修改"), {
    status: 409,
  });
  reviewBatchApiMock.reviewBatch
    .mockResolvedValueOnce(completed)
    .mockResolvedValue(refreshed);
  reviewBatchApiMock.reviewBatchRecords.mockResolvedValue({
    items: [{ ...baseRecord, workflow_status: "resolved" }],
    total: 1,
    page: 1,
    page_size: 20,
  });
  reviewBatchApiMock.publishReviewBatch
    .mockRejectedValueOnce(conflict)
    .mockResolvedValue({ version_id: "classification-version-2", version: 2 });

  render(
    <ReviewBatchPage
      route={{ query: { review_batch_id: "review-batch-1" } }}
      notify={vi.fn()}
    />,
  );
  await userEvent.click(await screen.findByRole("button", { name: "发布派生版本" }));
  await userEvent.type(
    screen.getByPlaceholderText("必填：说明本次复核版本的发布原因"),
    "本批复核已完成",
  );
  await userEvent.click(screen.getByRole("button", { name: "确认生成新版本" }));

  expect(await screen.findByText(/已刷新批次，请重新确认后发布/)).toBeVisible();
  expect(window.location.hash).not.toContain("classification-version-2");

  await userEvent.click(screen.getByRole("button", { name: "确认生成新版本" }));
  await waitFor(() =>
    expect(reviewBatchApiMock.publishReviewBatch).toHaveBeenLastCalledWith(
      "review-batch-1",
      { expected_revision: 5, reason: "本批复核已完成" },
    ),
  );
  expect(window.location.hash).toContain("result_version_id=classification-version-2");
  expect(window.location.hash).toContain("tab=history");
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

  expect(await screen.findByText(/已发布为分类结果 v2/)).toBeVisible();
  expect(screen.getByRole("button", { name: /查看衍生版本/ })).toBeEnabled();
  expect(screen.getByRole("button", { name: /创建分析看板/ })).toBeEnabled();
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
