import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
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
    itemReviews: [],
    addedItems: [],
    coverageStatus: "complete",
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
  "明确业务诊断 %s 进入历史待判断分组且只读",
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
    expect(within(group).queryByRole("button", { name: "调整" })).toBeNull();
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
  expect(within(group).getByText("历史记录")).toBeVisible();
  expect(within(group).queryByRole("button", { name: "调整" })).toBeNull();
  expect(within(group).getByText("系统处理失败")).toBeVisible();
  expect(screen.getByText("系统异常 1")).toBeVisible();
});

test.each(["change_label", "no_tag_needed", "remove"])(
  "历史业务诊断 %s 调整与计数一致，页面不提供编辑操作",
  (action) => {
    const record = diagnosticRecord();
    record.classification.human_semantic_reviews = [
      {
        semantic_item_id: "diagnostic-1",
        action,
        label_code: "EXPERIENCE",
        sentiment: "POSITIVE",
      },
    ];
    render(<SemanticReviewLedger {...ledgerProps(record)} />);
    expect(
      screen.getByText(action === "change_label" ? "已归类 1" : "无需归类 1"),
    ).toBeVisible();
    expect(screen.getByText("待判断 0")).toBeVisible();
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText(/人工调整：/)).toBeVisible();
  },
);

test.each(["", "不属于原文的证据"])(
  "历史诊断 %s 保留缺少原文的事实提示",
  (evidence) => {
    render(<SemanticReviewLedger {...ledgerProps(diagnosticRecord(true, evidence))} />);
    expect(screen.getByRole("note")).toHaveTextContent("缺少可核对的原文证据");
    expect(screen.queryByRole("button")).toBeNull();
  },
);

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
  render(<SemanticReviewLedger {...ledgerProps(record)} />);
  expect(screen.getAllByText("正式补录观点")).toHaveLength(1);
  expect(
    within(screen.getByLabelText("语义核验清单")).getByText("人工补充观点"),
  ).toBeVisible();
  expect(screen.getByText("人工调整：修改标签")).toBeVisible();
});
