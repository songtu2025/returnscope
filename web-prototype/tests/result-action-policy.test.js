import { describe, expect, test } from "vitest";

import {
  isDashboardSelectable,
  resultActionPolicy,
  resultStateLabel,
} from "../src/features/classification-results/resultActionPolicy";

describe("分类结果状态与主操作", () => {
  test.each([
    ["ready", "可用", "create-dashboard", true],
    ["review_required", "需复核", "create-review", true],
    ["needs_review", "需复核", "create-review", true],
    ["unusable", "不可用", "view-blocker", false],
  ])("兼容 %s 并生成唯一主操作", (qualityStatus, label, action, selectable) => {
    const result = { version_id: "version-1", quality_status: qualityStatus };
    const policy = resultActionPolicy(result);

    expect(resultStateLabel(result)).toBe(label);
    expect(policy.primary.kind).toBe(action);
    expect(isDashboardSelectable(result)).toBe(selectable);
    if (qualityStatus === "unusable") expect(policy.blockingReason).not.toBe("");
  });

  test("复核派生版本以复核事实为准并允许创建看板", () => {
    const result = {
      version_id: "version-2",
      quality_status: "ready",
      publish_status: "published",
      source_review_batch_id: "batch-1",
    };

    expect(resultActionPolicy(result)).toMatchObject({
      state: "review-derived",
      label: "复核已发布",
      dashboardSelectable: true,
      primary: { kind: "view-derived", label: "查看衍生版本" },
      secondary: { kind: "create-dashboard", label: "创建分析看板" },
    });
  });

  test("已有新版复核批次时主操作改为进入批次", () => {
    const policy = resultActionPolicy(
      { version_id: "version-1", quality_status: "review_required" },
      { activeBatch: { id: "batch-1", status: "in_review" } },
    );

    expect(policy.primary).toEqual({
      kind: "enter-review",
      label: "进入复核批次",
      reviewBatchId: "batch-1",
    });
  });

  test("显式交付字段优先于旧质量字段", () => {
    const result = {
      version_id: "version-legacy-ready",
      quality_status: "ready",
      delivery_status: "needs_review",
      publish_origin: "original-classification",
      dashboard_eligibility: false,
      blocking_reasons: [
        { code: "needs_review", message: "分类结果必须先完成复核并发布派生版本" },
      ],
    };

    expect(resultActionPolicy(result)).toMatchObject({
      state: "needs_review",
      label: "需复核",
      dashboardSelectable: false,
      primary: { kind: "create-review", label: "创建复核批次" },
      blockingReason: "分类结果必须先完成复核并发布派生版本",
    });
  });

  test("显式复核来源优先识别为复核派生版本", () => {
    const result = {
      version_id: "version-derived",
      quality_status: "ready",
      publish_origin: "review-derived",
      dashboard_eligibility: true,
    };

    expect(resultActionPolicy(result).state).toBe("review-derived");
  });
});
