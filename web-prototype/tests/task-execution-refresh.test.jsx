import { act, cleanup, renderHook, waitFor, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithServerState as render } from "./renderWithServerState";
import { TaskMonitor } from "../src/features/task-runtime/TaskMonitor";
import { SWRConfig } from "swr";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { useTaskMonitorState } from "../src/features/task-runtime/useTaskMonitorState";
import { taskExecutionActions } from "../src/features/task-runtime/taskExecutionActions";

const api = vi.hoisted(() => ({
  tasks: vi.fn(),
  task: vi.fn(),
  controlTaskSegment: vi.fn(),
  eventUrl: vi.fn(),
}));
vi.mock("../src/api", () => ({ api }));
const task = {
  id: "synthetic",
  title: "合成任务",
  revision: 3,
  status: "paused",
  segments: [],
};
const updated = { ...task, revision: 4 };
beforeEach(() => {
  vi.resetAllMocks();
  api.tasks.mockResolvedValue([task]);
  api.task.mockResolvedValue(task);
  api.eventUrl.mockReturnValue("/api/tasks/synthetic/events");
  api.controlTaskSegment.mockResolvedValue(updated);
});
afterEach(cleanup);
function wrapper({ children }) {
  return (
    <SWRConfig
      value={{
        provider: () => new Map(),
        shouldRetryOnError: false,
        dedupingInterval: 0,
      }}
    >
      {children}
    </SWRConfig>
  );
}
function mount() {
  const notify = vi.fn();
  const props = { notify, onNavigate: vi.fn(), onChanged: vi.fn(), focusId: task.id };
  const hook = renderHook(
    () => {
      const state = useTaskMonitorState(props);
      return {
        ...state,
        actions: taskExecutionActions({ ...state, selected: task, notify }),
      };
    },
    { wrapper },
  );
  return { ...hook, notify };
}

test("真实SWR列表读取失败不覆盖已提交Listing结果，也不把成功返回false", async () => {
  const { result, notify } = mount();
  await waitFor(() => expect(result.current.selected?.revision).toBe(3));
  await waitFor(() => expect(result.current.loading).toBe(false));
  api.tasks.mockRejectedValueOnce(new Error("合成列表读取失败"));
  let saved;
  await act(async () => {
    saved = await result.current.actions.onSegmentAction("segment", "delete");
  });
  expect(saved).toBe(true);
  expect(result.current.selected).toEqual(updated);
  expect(result.current.tasks).toEqual([task]);
  expect(result.current.listError).toBe("合成列表读取失败");
  expect(result.current.actionError).toBe("");
  expect(notify).toHaveBeenCalledWith(
    "Listing 操作已提交，任务列表或关联数据刷新失败，请刷新后查看",
    "error",
  );
  expect(notify).not.toHaveBeenCalledWith("合成列表读取失败", "error");
  expect(api.controlTaskSegment).toHaveBeenCalledOnce();
  expect(api.tasks).toHaveBeenCalledTimes(2);
  await act(() => result.current.loadTasks());
  expect(api.tasks).toHaveBeenCalledTimes(3);
});

test("显式列表刷新真实失败返回false，保留缓存；恢复后返回true", async () => {
  const { result, notify } = mount();
  await waitFor(() => expect(result.current.loading).toBe(false));
  await waitFor(() => expect(result.current.tasks).toHaveLength(1));
  api.tasks.mockRejectedValueOnce(new Error("合成列表读取失败"));
  let success;
  await act(async () => {
    success = await result.current.loadTasks();
  });
  expect(success).toBe(false);
  expect(result.current.tasks).toEqual([task]);
  expect(result.current.listError).toBe("合成列表读取失败");
  expect(notify).toHaveBeenCalledWith("合成列表读取失败", "error");
  await act(async () => {
    success = await result.current.loadTasks();
  });
  expect(success).toBe(true);
  expect(result.current.listError).toBe("");
});

test("详情页列表刷新失败提供独立只读重试，不重发移除请求", async () => {
  const segment = {
    id: "segment",
    segment_key: "segment-key",
    status: "paused",
    agent_key: "footwear",
    scope: { listing: "SYNTHETIC" },
    record_count: 1,
    unique_comments: 1,
  };
  api.tasks.mockResolvedValue([{ ...task, segments: [segment] }]);
  api.task.mockResolvedValue({ ...task, segments: [segment] });
  api.controlTaskSegment.mockResolvedValue({ ...updated, segments: [] });
  const user = userEvent.setup();
  render(
    <TaskMonitor
      notify={vi.fn()}
      onNavigate={vi.fn()}
      onChanged={vi.fn()}
      focusId={task.id}
    />,
  );
  await user.click(await screen.findByLabelText("更多 Listing 操作：SYNTHETIC"));
  await user.click(screen.getByRole("button", { name: "移除 Listing" }));
  api.tasks.mockRejectedValueOnce(new Error("合成列表读取失败"));
  await user.click(screen.getByRole("button", { name: "确认移除 Listing" }));
  const refresh = await screen.findByRole("button", { name: "刷新任务列表" });
  expect(refresh.closest('[role="alert"]')).toHaveTextContent("操作结果已保留");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(api.controlTaskSegment).toHaveBeenCalledOnce();
  await user.click(refresh);
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "刷新任务列表" }),
    ).not.toBeInTheDocument(),
  );
  expect(api.controlTaskSegment).toHaveBeenCalledOnce();
  expect(api.tasks).toHaveBeenCalledTimes(3);
});
