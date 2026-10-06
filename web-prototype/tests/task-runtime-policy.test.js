import { expect, test } from "vitest";
import {
  canArchiveTask,
  matchesQuery,
  sortTasks,
  taskFilterGroup,
  taskSummary,
} from "../src/features/task-runtime/taskRegistryPolicy";

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

test("缺少片段时回退Listing数量，明确空片段不使用历史数量", () => {
  expect(taskSummary({ status: "completed", listing_count: 7 })).toMatchObject({
    total: 7,
    generated: 0,
    remaining: 7,
  });
  expect(
    taskSummary({ status: "completed", listing_count: 7, segments: [] }),
  ).toMatchObject({ total: 0, generated: 0, remaining: 0 });
});

test("未知品类不计入可执行数量，但仍提示需处理", () => {
  expect(
    taskSummary({
      status: "queued",
      segments: [
        { agent_key: "unknown", status: "blocked" },
        { agent_key: "synthetic", status: "queued" },
      ],
    }),
  ).toMatchObject({
    total: 1,
    issues: 0,
    needsAttention: true,
    issueDescription: "查看任务原因并处理",
  });
});

test.each([
  [undefined, "run_ready", 2, "部分排队"],
  [false, "run_ready", 2, "排队中"],
  [true, "block_all", 0, "部分排队"],
  [undefined, "block_all", 2, "排队中"],
  [undefined, "run_ready", 0, "排队中"],
])(
  "部分排队保持显式标记优先于快照：%s/%s/%s",
  (partial_queue, unresolved_policy, blocked_count, statusLabel) => {
    const task = {
      status: "queued",
      partial_queue,
      snapshot: { execution_plan: { unresolved_policy, summary: { blocked_count } } },
    };
    expect(taskSummary(task).statusLabel).toBe(statusLabel);
  },
);

test("质量说明按可用、需复核、不可用、未知排序，旧结果仍计入生成数", () => {
  const segments = ["ready", "review_required", "unusable", "unknown"].map(
    (result_quality_status) => ({
      agent_key: "synthetic",
      status: "completed",
      result_publish_status: "published",
      result_quality_status,
    }),
  );
  segments.push({
    agent_key: "synthetic",
    status: "completed",
    result_file_path: "synthetic.xlsx",
  });
  expect(taskSummary({ status: "completed", segments })).toMatchObject({
    generated: 5,
    ready: 1,
    reviews: 1,
    unusable: 1,
    unknown: 2,
    resultDescription: "1 个可用 · 1 个需复核 · 1 个不可用 · 2 个质量未确认",
  });
});

test("归档分组与最终状态选择保持独立，搜索覆盖原有六字段", () => {
  expect(taskFilterGroup({ status: "running", archived_at: "2026-10-01" })).toBe(
    "archived",
  );
  expect(canArchiveTask({ status: "running" })).toBe(false);
  expect(canArchiveTask({ status: "running", archived_at: "2026-10-01" })).toBe(true);
  for (const field of [
    "title",
    "store",
    "listing",
    "listing_search_text",
    "dataset_name",
    "owner_name",
  ])
    expect(matchesQuery({ [field]: "SYNTHETIC" }, "synthetic")).toBe(true);
  expect(matchesQuery({}, "synthetic")).toBe(false);
  expect(matchesQuery({}, "")).toBe(true);
});

test("排序复制原数组，同值保持顺序，更新时间缺失时回退创建时间", () => {
  const first = { id: "a", created_at: "2026-10-02", progress_percent: 10 };
  const second = {
    id: "b",
    created_at: "2026-10-01",
    updated_at: "2026-10-03",
    progress_percent: 10,
  };
  const values = [first, second];
  expect(sortTasks(values, "updated_desc")).toEqual([second, first]);
  expect(sortTasks(values, "progress_desc")).toEqual([first, second]);
  expect(sortTasks(values, "created_desc")).toEqual([first, second]);
  expect(values).toEqual([first, second]);
  expect(sortTasks(values, "progress_desc")).not.toBe(values);
});
