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
