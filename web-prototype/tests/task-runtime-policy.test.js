import { expect, test } from "vitest";
import { taskSummary } from "../src/features/task-runtime/taskRegistryPolicy";

test("执行完成不等于结果可用，发布失败和复核分别统计", () => {
  const summary = taskSummary({
    status: "paused",
    metrics: { review_count: 0 },
    segments: [
      { status: "completed", result_publish_status: "publishing" },
      { status: "completed", result_publish_status: "failed" },
      {
        status: "completed",
        result_publish_status: "published",
        result_quality_status: "ready",
      },
      {
        status: "completed",
        result_publish_status: "published",
        result_quality_status: "review_required",
      },
      {
        status: "completed",
        result_publish_status: "published",
        result_quality_status: "unusable",
      },
      { status: "completed", result_file_path: "old.xlsx" },
      { status: "paused" },
    ],
  });
  expect(summary).toMatchObject({
    total: 7,
    generated: 4,
    ready: 1,
    reviews: 1,
    unusable: 1,
    unknown: 1,
    issues: 3,
    remaining: 3,
  });
});

test("主动暂停保持中性，模型异常暂停需要处理", () => {
  expect(
    taskSummary({ status: "paused", segments: [{ status: "paused" }] }).needsAttention,
  ).toBe(false);
  expect(
    taskSummary({
      status: "paused",
      segments: [{ status: "paused", error: "连接失败" }],
    }).needsAttention,
  ).toBe(true);
});
