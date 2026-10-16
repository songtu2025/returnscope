import { useState } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, screen, waitFor, within, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithServerState as render } from "./renderWithServerState";
import { TaskDetail } from "../src/features/task-runtime/TaskDetail";
import { taskExecutionActions } from "../src/features/task-runtime/taskExecutionActions";

const api = vi.hoisted(() => ({ controlTaskSegment: vi.fn(), task: vi.fn() }));
vi.mock("../src/api", () => ({ api }));
let current;
const segment = (index, status = "paused") => ({
  id: `segment-${index}`,
  segment_key: `key-${index}`,
  agent_key: "synthetic",
  agent_family: "合成标准",
  status,
  scope: { listing: `DEMO-${index}`, store: "合成店铺" },
  record_count: 1,
  unique_comments: 1,
  progress_current: 0,
  progress_total: 1,
});
function Harness() {
  const [task, setTask] = useState(current);
  const actions = taskExecutionActions({
    selected: task,
    setSelected: setTask,
    setActionError: vi.fn(),
    notify: vi.fn(),
    loadTasks: async () => true,
    mutateCache: async () => {},
    loadSelected: async () => {
      const next = await api.task();
      setTask(next);
      return next;
    },
  });
  return (
    <TaskDetail
      task={task}
      events={[]}
      {...actions}
      actionError=""
      onClearActionError={vi.fn()}
      onTaskRenamed={vi.fn()}
      onArchive={vi.fn()}
      onPause={vi.fn()}
      onResume={vi.fn()}
      onRetry={vi.fn()}
      onViewClassification={vi.fn()}
      onPreflightReplan={vi.fn()}
      onReplan={vi.fn()}
    />
  );
}
beforeEach(() => {
  vi.resetAllMocks();
  current = {
    id: "synthetic",
    title: "合成任务",
    status: "paused",
    revision: 3,
    owner_name: "验收用户",
    created_at: "2026-10-16",
    segments: [segment(1), segment(2), segment(3)],
  };
  api.task.mockImplementation(async () => current);
  api.controlTaskSegment.mockImplementation(async (_id, key, action, payload) => {
    expect(payload.expected_revision).toBe(current.revision);
    current = {
      ...current,
      revision: current.revision + 1,
      segments: current.segments.map((item) =>
        item.segment_key !== key
          ? item
          : action === "delete"
            ? { ...item, deleted_at: "today" }
            : action === "pause" && item.status === "running"
              ? { ...item, requested_action: "pause", display_status: "pause_pending" }
              : { ...item, status: action === "resume" ? "queued" : "paused" },
      ),
    };
    return current;
  });
});
afterEach(cleanup);
const batch = () => within(screen.getByRole("region", { name: "批量 Listing 操作" }));
async function choosePage() {
  await userEvent.click(screen.getByRole("checkbox", { name: "选择当前页 Listing" }));
}
async function confirmResume(count) {
  await userEvent.click(
    batch().getByRole("button", { name: `继续／重新排队 ${count} 项` }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: `确认继续／重新排队 ${count} 项` }),
  );
}

test("跨页选择、表头半选及筛选/任务切换清理选择", async () => {
  current.segments = Array.from({ length: 21 }, (_, i) => segment(i + 1));
  const view = render(<Harness />);
  await choosePage();
  expect(batch().getByText("已选择 20 个 Listing")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "下一页" }));
  await userEvent.click(
    screen.getByRole("checkbox", { name: "选择 Listing：DEMO-21" }),
  );
  expect(batch().getByText("已选择 21 个 Listing")).toBeVisible();
  await userEvent.click(
    screen.getByRole("checkbox", { name: "选择 Listing：DEMO-21" }),
  );
  await userEvent.click(screen.getByRole("button", { name: "上一页" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "选择 Listing：DEMO-1" }));
  expect(
    screen.getByRole("checkbox", { name: "选择当前页 Listing" }).indeterminate,
  ).toBe(true);
  await userEvent.type(screen.getByRole("textbox", { name: "搜索 Listing" }), "DEMO-2");
  await waitFor(() => expect(screen.queryByText(/已选择 .* 个 Listing/)).toBeNull());
  view.unmount();
  current = { ...current, id: "another-task" };
  render(<Harness />);
  expect(screen.queryByRole("region", { name: "批量 Listing 操作" })).toBeNull();
});

test("混合状态确认执行范围，移除只确认一次且不填写原因", async () => {
  current.segments = [
    segment(1, "queued"),
    segment(2, "running"),
    segment(3, "completed"),
  ];
  render(<Harness />);
  await choosePage();
  await userEvent.click(batch().getByRole("button", { name: "暂停 2 项" }));
  const dialog = within(screen.getByRole("dialog", { name: "批量暂停 Listing" }));
  expect(dialog.getByText(/将跳过 1 项/)).toBeVisible();
  expect(dialog.getByText("DEMO-3 · 跳过：当前状态不支持本次操作")).toBeVisible();
  await userEvent.click(dialog.getByRole("button", { name: "确认暂停 2 项" }));
  await waitFor(() =>
    expect(batch().getByText(/已提交 2 项.*跳过 1 项/)).toBeVisible(),
  );
  expect(api.controlTaskSegment.mock.calls.map((call) => call[1])).toEqual([
    "key-1",
    "key-2",
  ]);
  expect(screen.getByText("正在暂停")).toBeVisible();
  await userEvent.click(batch().getByRole("button", { name: "移除 1 项" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("已有分类结果和看板保留");
  expect(screen.queryByRole("textbox", { name: /原因/ })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "确认移除 1 项" }));
  await waitFor(() =>
    expect(screen.queryByRole("checkbox", { name: "选择 Listing：DEMO-3" })).toBeNull(),
  );
  expect(api.controlTaskSegment).toHaveBeenLastCalledWith(
    "synthetic",
    "key-3",
    "delete",
    { expected_revision: 5, note: "" },
  );
});

test("批量提交期间防重复、禁止冲突动作，成功后清空已成功项", async () => {
  let finish;
  api.controlTaskSegment.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  render(<Harness />);
  await choosePage();
  await userEvent.click(batch().getByRole("button", { name: "继续／重新排队 3 项" }));
  await userEvent.click(
    screen.getByRole("button", { name: "确认继续／重新排队 3 项" }),
  );
  expect(screen.getByRole("button", { name: "正在提交…" })).toBeDisabled();
  expect(screen.getByRole("textbox", { name: "搜索 Listing" })).toBeDisabled();
  expect(screen.getByRole("tab", { name: "运行日志" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "正在提交…" }));
  await userEvent.keyboard("{Escape}");
  expect(screen.getByRole("dialog")).toBeVisible();
  expect(api.controlTaskSegment).toHaveBeenCalledTimes(1);
  current = {
    ...current,
    revision: 4,
    segments: [{ ...segment(1), status: "queued" }, segment(2), segment(3)],
  };
  await act(async () => finish(current));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(batch().getByText("已选择 0 个 Listing")).toBeVisible();
  expect(api.controlTaskSegment).toHaveBeenCalledTimes(3);
});

test("409停止后续项，重试只处理失败和未执行项并使用最新修订", async () => {
  render(<Harness />);
  api.controlTaskSegment
    .mockImplementationOnce(async () => {
      current = {
        ...current,
        revision: 4,
        segments: [{ ...segment(1), status: "queued" }, segment(2), segment(3)],
      };
      return current;
    })
    .mockRejectedValueOnce(Object.assign(new Error("合成409"), { status: 409 }));
  await choosePage();
  await confirmResume(3);
  await waitFor(() =>
    expect(batch().getByText(/失败 1 项.*未执行 1 项/)).toBeVisible(),
  );
  expect(api.controlTaskSegment).toHaveBeenCalledTimes(2);
  expect(batch().getByText("已选择 2 个 Listing")).toBeVisible();
  await confirmResume(2);
  await waitFor(() => expect(batch().getByText("已选择 0 个 Listing")).toBeVisible());
  expect(api.controlTaskSegment.mock.calls.map((call) => call[1])).toEqual([
    "key-1",
    "key-2",
    "key-2",
    "key-3",
  ]);
  expect(
    api.controlTaskSegment.mock.calls.map((call) => call[3].expected_revision),
  ).toEqual([3, 4, 4, 5]);
});

test("未知写入和GET失败阻止重复，切换标签/筛选不能绕过；恢复读取后不重复成功项", async () => {
  api.controlTaskSegment.mockImplementationOnce(async () => {
    current = {
      ...current,
      revision: 4,
      segments: [{ ...segment(1), status: "queued" }, segment(2), segment(3)],
    };
    throw new TypeError("合成结果未知");
  });
  api.task.mockRejectedValue(new Error("合成GET503"));
  render(<Harness />);
  await choosePage();
  await confirmResume(3);
  await screen.findByRole("button", { name: "重新读取任务状态" });
  expect(batch().getByRole("button", { name: "继续／重新排队 3 项" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "修改任务名称：合成任务" })).toBeDisabled();
  await userEvent.click(screen.getByRole("tab", { name: "运行日志" }));
  await userEvent.click(screen.getByRole("tab", { name: "Listing", exact: true }));
  await userEvent.selectOptions(
    screen.getByRole("combobox", { name: "按 Listing 状态筛选" }),
    "active",
  );
  expect(batch().getByRole("button", { name: "重新读取任务状态" })).toBeEnabled();
  expect(api.controlTaskSegment).toHaveBeenCalledTimes(1);
  api.task.mockImplementation(async () => current);
  await userEvent.click(batch().getByRole("button", { name: "重新读取任务状态" }));
  await waitFor(() =>
    expect(
      screen.queryByText("最新任务状态尚未读取成功，继续操作前请先刷新核对。"),
    ).toBeNull(),
  );
  await choosePage();
  await confirmResume(2);
  await waitFor(() => expect(api.controlTaskSegment).toHaveBeenCalledTimes(3));
  expect(
    api.controlTaskSegment.mock.calls.filter((call) => call[1] === "key-1"),
  ).toHaveLength(1);
});
