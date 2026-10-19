import { expect, test } from "vitest";
import { publishedTaskResults } from "../src/features/task-runtime/taskSegmentPolicy";
import {
  canArchiveTask,
  matchesQuery,
  sortTasks,
  taskFilterGroup,
  taskSummary,
} from "../src/features/task-runtime/taskRegistryPolicy";

test("任务有效结果复用发布状态判断，排除移除/删除/未发布/缺ID，按版本去重且保留待复核", () => {
  const valid = { result_version_id: "same", result_quality_status: "needs_review" };
  expect(
    publishedTaskResults({
      segments: [
        { ...valid },
        valid,
        { result_version_id: "removed", deleted_at: "2026-10-20" },
        { result_version_id: "deleted", result_deleted_at: "2026-10-20" },
        { result_version_id: "pending", result_publish_status: "pending" },
        { result_publish_status: "published" },
        { result_file_path: "legacy.xlsx" },
      ],
    }),
  ).toEqual([valid]);
  expect(publishedTaskResults({})).toEqual([]);
});

test("按发布情况统计结果，发布失败仍提示需处理", () => {
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
    issues: 1,
    resultDescription: "3 个已发布 · 1 个旧结果",
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

test("不因历史版本质量判定提示异常，旧结果仍计入生成数", () => {
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
    needsAttention: false,
    issues: 0,
    resultDescription: "4 个已发布 · 1 个旧结果",
  });
});

test("发布完成仍保留真实系统异常提示", () => {
  expect(
    taskSummary({
      status: "completed",
      segments: [
        {
          status: "completed",
          result_publish_status: "published",
          system_failure_count: 2,
        },
      ],
    }),
  ).toMatchObject({ needsAttention: true, issues: 1 });
});

test("归档分组与最终状态选择保持独立，搜索覆盖任务 ID 及原有字段", () => {
  expect(taskFilterGroup({ status: "running", archived_at: "2026-10-01" })).toBe(
    "archived",
  );
  expect(canArchiveTask({ status: "running" })).toBe(false);
  expect(canArchiveTask({ status: "running", archived_at: "2026-10-01" })).toBe(true);
  for (const field of [
    "id",
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
  const sameName = [
    { id: "task_alpha", title: "同名任务" },
    { id: "task_beta", title: "同名任务" },
  ];
  expect(sameName.filter((task) => matchesQuery(task, "task_beta"))).toEqual([
    sameName[1],
  ]);
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

test("当前结果已处理不会被历史运行失败标成待处理，有待复核时给出当前记录数量", () => {
  const task = {
    status: "partial",
    segments: [
      {
        status: "completed_with_errors",
        result_publish_status: "published",
        system_failure_count: 0,
        pending_review_count: 0,
      },
    ],
  };
  expect(taskSummary(task)).toMatchObject({
    needsAttention: false,
    statusLabel: "分析完成",
  });
  task.segments[0].pending_review_count = 36;
  expect(taskSummary(task)).toMatchObject({
    needsAttention: true,
    issues: 1,
    attentionDescription: "36 条记录待复核，请在下方 Listing 中处理。",
  });
});
