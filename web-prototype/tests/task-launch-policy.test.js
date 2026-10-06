import { expect, test } from "vitest";
import { taskLaunchCopy } from "../src/features/task-create/newTaskPolicy";

const ready = {
  blocked: false,
  canContinue: true,
  categoryCompletionRequired: false,
  countMismatch: false,
  noExecutable: false,
  partialPlan: false,
  planCounts: { executable: 7 },
  preflightStatus: "ready",
  requiresScopeConfirmation: false,
  scopeConfirmed: false,
  submitError: "",
  submitting: false,
  system: { my_running_tasks: 0 },
  unresolvedPolicy: "run_ready",
};

test.each([
  [{}, "开始分析", "确认任务名称与模型后，即可开始分析。"],
  [
    { submitting: true, submitError: "合成错误", categoryCompletionRequired: true },
    "请先补齐商品品类",
    "正在创建任务，请稍候…",
  ],
  [
    { submitError: "合成错误", countMismatch: true },
    "评论数量需要重新预检",
    "配置已保留，可以重试创建。",
  ],
  [
    { preflightStatus: "loading", noExecutable: true },
    "没有可执行评论",
    "正在检查数据，不会调用模型…",
  ],
  [{ preflightStatus: "idle" }, "开始分析", "正在检查数据，不会调用模型…"],
  [
    { preflightStatus: "error", blocked: true },
    "启动 7 组已就绪评论",
    "检查未完成，请在上方重新检查数据。",
  ],
  [
    { categoryCompletionRequired: true, countMismatch: true, noExecutable: true },
    "请先补齐商品品类",
    "请先补齐上方提示的商品品类。",
  ],
  [
    { countMismatch: true, noExecutable: true },
    "评论数量需要重新预检",
    "评论数量校验未通过，请重新检查数据。",
  ],
  [
    { noExecutable: true, blocked: true },
    "没有可执行评论",
    "当前范围没有可执行评论，请修改分析数据。",
  ],
  [
    { blocked: true, unresolvedPolicy: "" },
    "选择处理方式后继续",
    "请在上方选择未解决问题的处理方式。",
  ],
  [
    { blocked: true, unresolvedPolicy: "block_all" },
    "保存任务，等待问题处理",
    "仅保存任务，处理完数据问题后再开始分析。",
  ],
  [
    { blocked: true, unresolvedPolicy: "run_ready" },
    "启动 7 组已就绪评论",
    "确认任务名称与模型后，即可开始分析。",
  ],
  [
    { partialPlan: true, requiresScopeConfirmation: true },
    "启动 7 组可执行评论",
    "请先确认上方的分析范围与排除项。",
  ],
  [
    {
      partialPlan: true,
      requiresScopeConfirmation: true,
      scopeConfirmed: true,
      system: { my_running_tasks: 3 },
    },
    "启动 7 组可执行评论",
    "并行名额已满，启动后将进入队列。",
  ],
])("启动提示保留阻断与异步状态的优先级：%s", (changes, submitLabel, launchStatus) => {
  expect(taskLaunchCopy({ ...ready, ...changes })).toEqual({
    launchStatus,
    submitLabel,
  });
});
