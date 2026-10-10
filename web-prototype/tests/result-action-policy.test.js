import { describe, expect, test } from "vitest";
import {
  isDashboardSelectable,
  resultActionPolicy,
  resultStateLabel,
  resultVersionId,
} from "../src/features/classification-results/resultActionPolicy";

describe("分类版本由用户决定是否使用", () => {
  test.each(["ready", "review_required", "unusable"])(
    "已发布的 %s 版本不再整体阻断",
    (quality_status) => {
      const result = {
        version_id: "synthetic-version",
        publish_status: "published",
        quality_status,
        dashboard_eligibility: false,
        blocking_reasons: [{ code: "unusable", message: "旧版质量阻断" }],
      };
      expect(isDashboardSelectable(result)).toBe(true);
      expect(resultActionPolicy(result)).toMatchObject({
        label: "已发布",
        dashboardSelectable: true,
        primary: { kind: "create-dashboard", disabled: false },
        blockingReason: "",
      });
    },
  );

  test.each(["publishing", "failed", undefined])(
    "未发布版本保留实际执行限制：%s",
    (publish_status) => {
      const result = { quality_status: "ready", publish_status };
      expect(isDashboardSelectable(result)).toBe(false);
      expect(resultActionPolicy(result)).toMatchObject({
        primary: { disabled: true },
        blockingReason: "分类结果版本尚未发布",
      });
    },
  );

  test.each([
    ["ready", "可用"],
    ["review_required", "需复核"],
    ["unusable", "不可用"],
  ])("记录级 %s 状态仍作为判断依据", (quality_status, label) => {
    expect(resultStateLabel({ quality_status })).toBe(label);
  });
});

test("结果版本编号仍使用明确版本字段优先", () => {
  expect(
    resultVersionId({
      version_id: "current",
      result_version_id: "legacy",
      id: "fallback",
    }),
  ).toBe("current");
  expect(resultVersionId({ result_version_id: "legacy", id: "fallback" })).toBe(
    "legacy",
  );
});
