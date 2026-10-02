import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { SemanticReviewLedger } from "../src/features/review-batches/SemanticReviewLedger";
import { semanticReviewLedger } from "../src/features/review-batches/semanticReviewPresentation";

afterEach(cleanup);

const labels = [
  {
    code: "EXPERIENCE",
    name: "使用体验",
    allowed_sentiments: ["POSITIVE", "NEGATIVE", "NEUTRAL"],
  },
];

function ledgerProps(record = {}) {
  return {
    record,
    labels,
    editable: true,
    itemReviews: [],
    addedItems: [],
    coverageStatus: "complete",
    onItemReviews: vi.fn(),
    onAddedItems: vi.fn(),
    onCoverageStatus: vi.fn(),
  };
}

function diagnosticRecord(businessReviewRequired = true, evidence = "鞋子非常舒服") {
  return {
    comment: "鞋子非常舒服，尺码也合适。",
    classification: {
      semantic_review: {
        semantic_items: [
          {
            item_id: "diagnostic-1",
            evidence_text: evidence,
            evidence_source: "SYSTEM",
            opinion: "标签规则要求人工复核",
            disposition: "ANALYSIS_FAILURE",
            business_review_required: businessReviewRequired,
            diagnostic_title: "标签规则要求人工复核",
            diagnostic_domain: "SEMANTIC_ANALYSIS_QUALITY",
          },
        ],
      },
    },
  };
}

test.each(["ANALYSIS_FAILURE", "MODEL_ERROR"])(
  "明确业务诊断 %s 进入待判断分组并可编辑",
  (disposition) => {
    const record = diagnosticRecord();
    record.classification.semantic_review.semantic_items[0].disposition = disposition;
    const data = semanticReviewLedger(record);
    expect(data.summary).toEqual({
      mapped: 0,
      informational: 0,
      needsReview: 1,
      failures: 0,
    });
    render(<SemanticReviewLedger {...ledgerProps(record)} />);
    const group = screen.getByRole("region", { name: "待人工判断" });
    expect(within(group).getByRole("button", { name: "调整" })).toBeEnabled();
    expect(screen.getByText("待判断 1")).toBeVisible();
    expect(screen.getByText("系统异常 0")).toBeVisible();
    expect(screen.queryByText("已锁定编辑")).toBeNull();
    expect(screen.queryByText("系统处理失败")).toBeNull();
    expect(screen.getByText("诊断提示")).toBeVisible();
  },
);

test.each([
  [false, "change_label"],
  [false, "no_tag_needed"],
  [false, "remove"],
  ["legacy", "change_label"],
  ["legacy", "no_tag_needed"],
  ["legacy", "remove"],
])("技术诊断或旧诊断 %s 的 %s 修改不生效且保持锁定", (flag, action) => {
  const record = diagnosticRecord(false);
  if (flag === "legacy")
    delete record.classification.semantic_review.semantic_items[0]
      .business_review_required;
  render(
    <SemanticReviewLedger
      {...ledgerProps(record)}
      itemReviews={[
        {
          semantic_item_id: "diagnostic-1",
          action,
          label_code: "EXPERIENCE",
          sentiment: "POSITIVE",
        },
      ]}
    />,
  );
  const group = screen.getByRole("region", { name: "系统异常" });
  expect(within(group).getByText("已锁定编辑")).toBeVisible();
  expect(within(group).queryByRole("button", { name: "调整" })).toBeNull();
  expect(within(group).getByText("系统处理失败")).toBeVisible();
  expect(screen.getByText("系统异常 1")).toBeVisible();
});

test.each(["change_label", "no_tag_needed", "remove"])(
  "业务诊断 %s 调整、计数、撤销和重新打开一致",
  async (action) => {
    const record = diagnosticRecord();
    const props = ledgerProps(record);
    const view = render(<SemanticReviewLedger {...props} />);
    await userEvent.click(screen.getByRole("button", { name: "调整" }));
    if (action === "change_label") {
      await select("修改观点标签：标签规则要求人工复核", "使用体验 · EXPERIENCE");
      expect(screen.getByRole("button", { name: "保存本项调整" })).toBeDisabled();
      await select("观点评价方向：标签规则要求人工复核", "正向");
    } else {
      await select(
        "调整方式：标签规则要求人工复核",
        action === "remove" ? "删除错误提取" : "标记为无需归类",
      );
    }
    await userEvent.click(screen.getByRole("button", { name: "保存本项调整" }));
    const reviews = props.onItemReviews.mock.calls[0][0];
    expect(reviews[0]).toMatchObject({ semantic_item_id: "diagnostic-1", action });
    if (action === "change_label") expect(reviews[0].sentiment).toBe("POSITIVE");
    view.rerender(<SemanticReviewLedger {...props} itemReviews={reviews} />);
    const countLabel = action === "change_label" ? "已归类 1" : "无需归类 1";
    expect(screen.getByText(countLabel)).toBeVisible();
    expect(screen.getByText("待判断 0")).toBeVisible();
    expect(screen.getByText("系统异常 0")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "撤销调整" }));
    expect(props.onItemReviews).toHaveBeenLastCalledWith([]);
    view.rerender(<SemanticReviewLedger {...props} itemReviews={[]} />);
    expect(screen.getByText("待判断 1")).toBeVisible();
    const saved = {
      ...record,
      classification: { ...record.classification, human_semantic_reviews: reviews },
    };
    view.rerender(<SemanticReviewLedger {...ledgerProps(saved)} editable={false} />);
    expect(screen.getByText(countLabel)).toBeVisible();
    expect(screen.getByText("待判断 0")).toBeVisible();
    expect(screen.queryByRole("button", { name: /调整/ })).toBeNull();
    expect(screen.getByText(/人工调整：/)).toBeVisible();
  },
);

test.each(["", "不属于原文的证据"])(
  "缺少可核对原文 %s 时提示补录并只允许移除错误诊断",
  async (evidence) => {
    const props = ledgerProps(diagnosticRecord(true, evidence));
    render(<SemanticReviewLedger {...props} />);
    expect(screen.getByRole("note")).toHaveTextContent("补充遗漏观点");
    await userEvent.click(screen.getByRole("button", { name: "调整" }));
    await select("修改观点标签：标签规则要求人工复核", "使用体验 · EXPERIENCE");
    await select("观点评价方向：标签规则要求人工复核", "正向");
    expect(screen.getByRole("button", { name: "保存本项调整" })).toBeDisabled();
    await select("调整方式：标签规则要求人工复核", "标记为无需归类");
    expect(screen.getByRole("button", { name: "保存本项调整" })).toBeDisabled();
    await select("调整方式：标签规则要求人工复核", "删除错误提取");
    await userEvent.click(screen.getByRole("button", { name: "保存本项调整" }));
    expect(props.onItemReviews).toHaveBeenCalledWith([
      expect.objectContaining({ action: "remove" }),
    ]);
  },
);

async function select(label, option) {
  const input = screen.getByRole("combobox", { name: label });
  fireEvent.mouseDown(
    input.closest(".ant-select").querySelector(".ant-select-content"),
  );
  await userEvent.click(
    await screen.findByText(option, { selector: ".ant-select-item-option-content" }),
  );
}

test("补录多方向标签需要明确选择评价方向", async () => {
  const props = ledgerProps();
  render(<SemanticReviewLedger {...props} />);
  await userEvent.click(screen.getByRole("button", { name: "补充遗漏观点" }));
  await userEvent.type(
    screen.getByPlaceholderText("粘贴能够支持该观点的原文片段"),
    "合成原文",
  );
  await userEvent.type(
    screen.getByPlaceholderText("用一句话概括用户表达的观点"),
    "合成正面观点",
  );
  await select("补充观点的归类标签", "使用体验 · EXPERIENCE");
  const add = screen.getByRole("button", { name: "添加观点" });
  expect(add).toBeDisabled();
  await select("补充观点的评价方向", "正向");
  expect(add).toBeEnabled();
  await userEvent.click(add);
  expect(props.onAddedItems).toHaveBeenCalledWith([
    expect.objectContaining({ sentiment: "POSITIVE" }),
  ]);
});

test("未知项方向待定时不能保存标签更正", async () => {
  const props = ledgerProps({
    classification: {
      semantic_review: {
        semantic_items: [
          {
            item_id: "unknown-1",
            opinion: "待定观点",
            evidence_text: "合成原文",
            disposition: "TAXONOMY_GAP",
          },
        ],
      },
    },
  });
  render(<SemanticReviewLedger {...props} />);
  await userEvent.click(screen.getByRole("button", { name: "调整" }));
  await select("修改观点标签：待定观点", "使用体验 · EXPERIENCE");
  const save = screen.getByRole("button", { name: "保存本项调整" });
  expect(save).toBeDisabled();
  await select("观点评价方向：待定观点", "中性");
  await userEvent.click(save);
  expect(props.onItemReviews).toHaveBeenCalledWith([
    expect.objectContaining({
      semantic_item_id: "unknown-1",
      action: "change_label",
      sentiment: "NEUTRAL",
    }),
  ]);
});

test("发布后的补录只展示一次且保留原始人工调整关联", () => {
  const record = {
    classification: {
      semantic_review: {
        semantic_items: [
          {
            item_id: "fact:manual:1",
            fact_id: "manual:1",
            opinion: "正式补录观点",
            evidence_text: "合成原文",
            label_code: "EXPERIENCE",
            disposition: "MAPPED",
          },
        ],
      },
      human_added_semantic_items: [
        {
          item_id: "manual-1",
          result_item_id: "fact:manual:1",
          applied: true,
          opinion: "正式补录观点",
          evidence_text: "合成原文",
          label_code: "EXPERIENCE",
        },
      ],
      human_semantic_reviews: [
        {
          semantic_item_id: "旧的哈希编号",
          result_item_id: "fact:manual:1",
          applied: true,
          action: "change_label",
          label_code: "EXPERIENCE",
        },
      ],
    },
  };
  const data = semanticReviewLedger(record);
  expect(data.items).toHaveLength(1);
  expect(data.items[0].review.semantic_item_id).toBe("旧的哈希编号");
  render(<SemanticReviewLedger {...ledgerProps(record)} editable={false} />);
  expect(screen.getAllByText("正式补录观点")).toHaveLength(1);
  expect(
    within(screen.getByLabelText("语义核验清单")).getByText("人工补充观点"),
  ).toBeVisible();
  expect(screen.getByText("人工调整：修改标签")).toBeVisible();
});
