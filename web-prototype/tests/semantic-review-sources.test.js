import { expect, test } from "vitest";
import {
  normalizeItem,
  suppliedItems,
  suppliedSummary,
  reviewedLedgerItems,
} from "../src/features/review-batches/semanticReviewSources";

test("空语义项保留默认投影与编号", () => {
  expect(normalizeItem({}, 7)).toEqual({
    id: "semantic-item-7",
    evidence: "无文本证据",
    evidenceSource: "",
    opinion: "旧结果未提供独立观点",
    labelCode: "",
    labelPath: [],
    disposition: "UNKNOWN",
    reason: "",
    diagnosticDomain: "",
    diagnosticCode: "",
    diagnosticTitle: "",
    detailStatus: "",
    primaryResult: "",
    secondaryResult: "",
    diagnosticDetail: "",
    diagnosticAction: "",
    businessReviewRequired: undefined,
    manual: false,
    sentiment: "",
  });
});

test.each([
  ["semantic_item_id", "semantic-1"],
  ["item_id", "item-1"],
  ["fact_id", "fact-1"],
  ["factId", "camel-1"],
  ["id", "id-1"],
])("语义项编号保留 %s 的优先级", (key, id) => {
  const candidates = {
    semantic_item_id: "semantic-1",
    item_id: "item-1",
    fact_id: "fact-1",
    factId: "camel-1",
    id: "id-1",
  };
  for (const name of Object.keys(candidates)) {
    if (name === key) break;
    candidates[name] = "";
  }
  expect(normalizeItem(candidates, 0).id).toBe(id);
});

test("诊断字段先选非空下划线值，布尔标记按空值而非真值回退", () => {
  const item = normalizeItem(
    {
      diagnostic_domain: "领域甲",
      diagnosticDomain: "领域乙",
      diagnostic_code: "",
      diagnosticCode: "代码乙",
      code: "旧代码",
      diagnostic_title: null,
      diagnosticTitle: "标题乙",
      title: "旧标题",
      detail_status: "状态甲",
      detailStatus: "状态乙",
      primary_result: "",
      primaryResult: "主要结果乙",
      secondary_result: null,
      secondaryResult: "次要结果乙",
      detail: "说明甲",
      diagnosticDetail: "说明乙",
      action: "",
      diagnosticAction: "行动乙",
      business_review_required: false,
      businessReviewRequired: true,
      disposition: "ANALYSIS_FAILURE",
      extra: "保留原字段",
    },
    0,
  );
  expect(item).toMatchObject({
    diagnosticDomain: "领域甲",
    diagnosticCode: "代码乙",
    diagnosticTitle: "标题乙",
    detailStatus: "状态甲",
    primaryResult: "主要结果乙",
    secondaryResult: "次要结果乙",
    diagnosticDetail: "说明甲",
    diagnosticAction: "行动乙",
    businessReviewRequired: false,
    disposition: "ANALYSIS_FAILURE",
    extra: "保留原字段",
  });
});

test.each(["ANALYSIS_FAILURE", "MODEL_ERROR"])(
  "%s 只有明确布尔业务标记才进入待判断",
  (disposition) => {
    expect(
      normalizeItem({ disposition, businessReviewRequired: true }, 0).disposition,
    ).toBe("UNKNOWN");
    expect(
      normalizeItem(
        { disposition, business_review_required: false, businessReviewRequired: true },
        0,
      ).disposition,
    ).toBe(disposition);
    expect(
      normalizeItem({ disposition, businessReviewRequired: "true" }, 0).disposition,
    ).toBe(disposition);
  },
);

test("证据片段保留原序、分隔符和空数组标签路径", () => {
  const labelPath = [];
  const item = normalizeItem(
    {
      evidence_spans: [
        { text: "甲", source: "A" },
        null,
        { text: "", source: "" },
        { text: "乙", source: "B" },
      ],
      label_path: labelPath,
      taxonomy_path: ["旧标签"],
      label_code: "LABEL",
    },
    0,
  );
  expect(item.evidence).toBe("甲 … 乙");
  expect(item.evidenceSource).toBe("A+B");
  expect(item.labelPath).toBe(labelPath);
  expect(item.disposition).toBe("MAPPED");
});

test("根语义清单与汇总优先，空清单不回退到分类清单", () => {
  const record = {
    semantic_review: {
      semantic_items: [],
      coverage_summary: {
        mapped: 0,
        taxonomy_gap: 2,
        true_ambiguity: 3,
        unexplained_fragment_count: 1,
      },
    },
    classification: {
      semantic_review: {
        semantic_items: [{ item_id: "旧项" }],
        coverage_summary: { mapped: 99 },
      },
    },
  };
  expect(suppliedItems(record)).toBe(record.semantic_review.semantic_items);
  expect(suppliedSummary(record)).toEqual({
    mapped: 0,
    informational: 0,
    needsReview: 6,
    failures: 0,
  });
});

test("已发布人工调整按结果编号关联并保持输入对象不变", () => {
  const original = normalizeItem({ item_id: "result-1" }, 0);
  const review = {
    semantic_item_id: "old-1",
    result_item_id: "result-1",
    applied: true,
  };
  const [item] = reviewedLedgerItems([original], {
    human_semantic_reviews: [review],
    human_added_semantic_items: [{ applied: true, result_item_id: "result-1" }],
  });
  expect(item).toMatchObject({ review, manual: true, applied: true });
  expect(item.review).toBe(review);
  expect(original.manual).toBe(false);
  expect(original).not.toHaveProperty("review");
});
