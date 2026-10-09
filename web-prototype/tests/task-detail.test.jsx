import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { renderWithServerState as render } from "./renderWithServerState";

vi.mock("../src/features/task-runtime/SegmentBoard", () => ({
  SegmentBoard: ({ initialFilter, focusSegmentId, onRetry }) => (
    <div aria-label="合成 Listing 面板">
      <span>{initialFilter}</span>
      <span>{focusSegmentId || "未指定焦点"}</span>
      <button onClick={() => onRetry({ segment_key: "synthetic-segment" })}>
        重试合成片段
      </button>
    </div>
  ),
}));

vi.mock("../src/features/task-runtime/TaskActionDialogs", () => ({
  TaskRenameDialog: ({ onSave }) => (
    <button onClick={() => onSave({ title: "合成新名称" })}>保存合成名称</button>
  ),
  TaskCancelDialog: () => null,
  TaskResumeDialog: () => null,
  SegmentCancelDialog: () => null,
  SegmentRetryDialog: ({ error, onSave }) => (
    <div role="dialog" aria-label="合成片段重试">
      <span>{error}</span>
      <button onClick={() => onSave({ note: "合成重试原因" })}>保存合成重试</button>
    </div>
  ),
}));

import { TaskDetail } from "../src/features/task-runtime/TaskDetail";

afterEach(cleanup);

function detailProps(task = {}) {
  return {
    task: {
      id: "synthetic-task",
      title: "合成任务",
      status: "running",
      revision: 1,
      owner_name: "合成用户",
      created_at: "2026-10-01T00:00:00Z",
      segments: [],
      ...task,
    },
    events: [],
    actionError: "",
    onClearActionError: vi.fn(),
    onRename: vi.fn().mockResolvedValue(true),
    onArchive: vi.fn(),
    onCancel: vi.fn(),
    onPause: vi.fn(),
    onResume: vi.fn(),
    onRetry: vi.fn(),
    onRetrySegment: vi.fn().mockResolvedValue(true),
    onRetryResultPublish: vi.fn(),
    onSegmentAction: vi.fn(),
    onParallelism: vi.fn(),
    onReorderSegments: vi.fn(),
    onPreflightReplan: vi.fn(),
    onReplan: vi.fn(),
    onViewClassification: vi.fn(),
  };
}

test("任务配置使用固化快照，并从可执行片段选择分类标准", async () => {
  render(
    <TaskDetail
      {...detailProps({
        connection_name: "合成旧连接",
        config_version: 9,
        primary_model: "合成旧模型",
        primary_effort: "low",
        segments: [
          { agent_key: "unknown", standard_name: "不可执行标准", status: "blocked" },
          { agent_key: "footwear", standard_name: "合成标准", status: "completed" },
        ],
        snapshot: {
          config: {
            connection: "合成快照连接",
            version: 0,
            primary_model: "合成快照模型",
            primary_effort: "high",
            strategy_source: "task",
          },
        },
      })}
    />,
  );
  await userEvent.click(screen.getByRole("tab", { name: "任务配置" }));
  expect(screen.getByText("合成快照连接 · #0 · 任务自定义")).toBeVisible();
  expect(screen.getByText("合成快照模型 · 高")).toBeVisible();
  expect(screen.getByText("合成标准")).toBeVisible();
  expect(screen.queryByText("不可执行标准")).not.toBeInTheDocument();
  expect(screen.queryByText("合成旧模型 · 低")).not.toBeInTheDocument();
});

test("历史任务配置回退到基础字段，并保留默认并行数与空值", async () => {
  render(
    <TaskDetail
      {...detailProps({
        connection_name: "合成基础连接",
        config_version: 2,
        primary_model: "合成基础模型",
        primary_effort: "medium",
      })}
    />,
  );
  await userEvent.click(screen.getByRole("tab", { name: "任务配置" }));
  expect(screen.getByText("合成基础连接 · #2")).toBeVisible();
  expect(screen.getByText("合成基础模型 · 中")).toBeVisible();
  expect(screen.getByText("3")).toBeVisible();
  expect(screen.getAllByText("— · v—")).toHaveLength(2);
});

test("总览展示评论进度和发布情况，并通过需处理入口切换 Listing", async () => {
  render(
    <TaskDetail
      {...detailProps({
        progress_percent: 49.6,
        progress_current: 1000,
        progress_total: 2000,
        segments: [
          {
            agent_key: "footwear",
            status: "completed",
            result_version_id: "synthetic-result",
            result_publish_status: "published",
            result_quality_status: "ready",
          },
          { agent_key: "footwear", status: "failed" },
        ],
      })}
    />,
  );
  const overview = screen.getByRole("region", { name: "任务运行总览" });
  expect(within(overview).getByText("50%")).toBeVisible();
  expect(within(overview).getByText("1,000 / 2,000 组评论")).toBeVisible();
  expect(within(overview).getByText("1 个已发布")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "查看需处理事项" }));
  expect(
    within(screen.getByLabelText("合成 Listing 面板")).getByText("attention"),
  ).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "查看已有结果" }));
  expect(
    within(screen.getByLabelText("合成 Listing 面板")).getByText("delivered"),
  ).toBeVisible();
});

test.each([
  ["paused", 1, "模型服务异常，任务已自动暂停"],
  ["paused", 0, "模型服务异常，任务已暂停"],
  ["failed", 0, "模型服务异常，执行已停止"],
  ["running", 0, "模型服务异常，请检查连接与运行日志"],
])("模型服务告警保持状态文案：%s/%s", (status, pauseRequested, label) => {
  render(
    <TaskDetail
      {...detailProps({
        status,
        pause_requested: pauseRequested,
        segments: [
          {
            agent_key: "unknown",
            status: "failed",
            model_failures: 9,
            error: "排除合成异常",
          },
          {
            agent_key: "footwear",
            status,
            model_failures: 3,
            model_calls: 2,
            cache_hits: 1,
            error: "合成模型异常",
          },
        ],
      })}
    />,
  );
  expect(screen.getByText(label)).toBeVisible();
  expect(screen.getByText("成功 2 · 失败 3 · 缓存 1")).toBeVisible();
  expect(screen.queryByText("排除合成异常")).not.toBeInTheDocument();
});

test("重试片段时错误留在弹窗内，失败保留弹窗，成功后关闭", async () => {
  const props = detailProps();
  props.actionError = "合成保存失败";
  props.onRetrySegment.mockResolvedValueOnce(false).mockResolvedValueOnce(true);
  render(<TaskDetail {...props} />);
  expect(screen.getByRole("alert")).toHaveTextContent("合成保存失败");
  await userEvent.click(screen.getByRole("button", { name: "重试合成片段" }));
  expect(props.onClearActionError).toHaveBeenCalledOnce();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByRole("dialog")).toHaveTextContent("合成保存失败");
  await userEvent.click(screen.getByRole("button", { name: "保存合成重试" }));
  expect(screen.getByRole("dialog")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "保存合成重试" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(props.onRetrySegment).toHaveBeenLastCalledWith("synthetic-segment", {
    note: "合成重试原因",
  });
});

test("重命名保存失败保留弹窗，成功关闭，列表焦点变化恢复执行页", async () => {
  const props = detailProps();
  props.onRename.mockResolvedValueOnce(false).mockResolvedValueOnce(true);
  const view = render(<TaskDetail {...props} />);
  await userEvent.click(screen.getByLabelText("更多任务操作"));
  await userEvent.click(screen.getByRole("button", { name: "修改名称" }));
  await userEvent.click(screen.getByRole("button", { name: "保存合成名称" }));
  expect(screen.getByRole("button", { name: "保存合成名称" })).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "保存合成名称" }));
  expect(
    screen.queryByRole("button", { name: "保存合成名称" }),
  ).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("tab", { name: "任务配置" }));
  view.rerender(<TaskDetail {...props} focusSegmentId="synthetic-focus" />);
  expect(screen.getByRole("tab", { name: "Listing" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  expect(screen.getByText("synthetic-focus")).toBeVisible();
});
