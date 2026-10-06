import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import {
  defaultReviewAssessment,
  reviewAssessment,
  reviewAssessmentLabel,
  REVIEW_ASSESSMENT_FIELDS,
} from "../src/features/review-batches/reviewAssessment";
import { ReviewRecordEvidence } from "../src/features/review-batches/ReviewRecordEvidence";

afterEach(cleanup);

test.each([
  ["confirm", ["correct", "complete", "correct"]],
  ["modify", ["partial", "partial", "should_manual_review"]],
  ["exclude", ["not_applicable", "missing", "correct"]],
])("%s 复核默认判断保留且每次返回独立对象", (action, values) => {
  const first = defaultReviewAssessment(action);
  expect(Object.values(first)).toEqual(values);
  first.labelCorrectness = "合成修改";
  expect(Object.values(defaultReviewAssessment(action))).toEqual(values);
});

test("分类中的空判断对象优先于根旧判断，空字段使用动作默认值", () => {
  const record = {
    human_review_assessment: { label_correctness: "incorrect" },
    classification: {
      human_review_assessment: {
        label_correctness: "",
        evidence_completeness: "missing",
      },
    },
  };
  expect(reviewAssessment(record, "modify")).toEqual({
    labelCorrectness: "partial",
    evidenceCompleteness: "missing",
    reviewRouting: "should_manual_review",
  });
  record.classification.human_review_assessment = {};
  expect(reviewAssessment(record).labelCorrectness).toBe("correct");
});

test("分类判断缺失时沿用根旧判断", () => {
  expect(
    reviewAssessment({
      human_review_assessment: {
        label_correctness: "incorrect",
        review_routing: "should_auto_approve",
      },
    }),
  ).toEqual({
    labelCorrectness: "incorrect",
    evidenceCompleteness: "complete",
    reviewRouting: "should_auto_approve",
  });
});

test.each(REVIEW_ASSESSMENT_FIELDS)("$label 保留已知选项及未知值反馈", (field) => {
  for (const [code, label] of field.options)
    expect(reviewAssessmentLabel(field, code)).toBe(label);
  expect(reviewAssessmentLabel(field, undefined)).toBe("未单独记录");
  expect(reviewAssessmentLabel(field, "合成未知值")).toBe("未单独记录");
});

test.each([true, false])(
  "复核证据区 editable=%s 保留展示区域与质量判断条件",
  (editable) => {
    const record = {
      id: "synthetic-review-1",
      comment: "合成原文上下文",
      product_names: ["合成商品"],
      record_count: 8,
      classification: {
        human_review_assessment: {
          label_correctness: "partial",
          evidence_completeness: "missing",
          review_routing: "correct",
        },
      },
    };
    const { container } = render(
      <ReviewRecordEvidence
        record={record}
        editable={editable}
        labels={[]}
        semanticItemReviews={[]}
        addedSemanticItems={[]}
      />,
    );
    expect(container.querySelector(".review-business-evidence")).toHaveTextContent(
      "合成商品",
    );
    expect(container.querySelector(".review-source-context")).toHaveTextContent(
      "合成原文上下文",
    );
    expect(container.querySelector(".review-primary-context")).toHaveTextContent(
      "未形成主因标签",
    );
    if (editable) expect(screen.queryByLabelText("已保存的复核质量判断")).toBeNull();
    else
      expect(screen.getByLabelText("已保存的复核质量判断")).toHaveTextContent(
        "部分正确证据完整性缺失路由合理性路由正确",
      );
  },
);
