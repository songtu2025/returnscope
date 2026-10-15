import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { TaskRuntimePage } from "../src/features/task-runtime/TaskRuntimePage";
import { useHashRoute } from "../src/app/hashRouter";
import { renderWithServerState as render } from "./renderWithServerState";
import { refreshTaskNameState, serverStateKeys } from "../src/shared/serverState";
import { useTaskMonitorState } from "../src/features/task-runtime/useTaskMonitorState";
import { useEffect } from "react";
const api = vi.hoisted(() => ({ tasks: vi.fn(), archiveTasks: vi.fn() }));
vi.mock("../src/api", () => ({ api }));
const source = [
  ["mine-running", "me", "running"],
  ["mine-queued", "me", "queued"],
  ["mine-paused", "me", "paused"],
  ["mine-done", "me", "completed"],
  ["other-running", "other", "running"],
].map(([id, owner, status]) => ({
  id,
  owner,
  status,
  title: id,
  owner_name: "同名用户",
  store: "TEST",
  created_at: "2026-10-01T00:00:00Z",
  segments: [],
}));
const archived = {
  ...source[0],
  id: "mine-archived",
  title: "mine-archived",
  archived_at: "2026-10-01T00:00:00Z",
};
function Harness() {
  const { route } = useHashRoute();
  return (
    <TaskRuntimePage
      route={route}
      userId="me"
      notify={vi.fn()}
      onNavigate={vi.fn()}
      onChanged={vi.fn()}
    />
  );
}
beforeEach(() => {
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  api.tasks
    .mockReset()
    .mockImplementation(async (filters) =>
      [...source, archived]
        .filter((task) => !filters.owner_id || task.owner === filters.owner_id)
        .map(({ owner: _owner, ...task }) => task),
    );
  window.history.replaceState(null, "", "#analysis-tasks?scope=mine&status=active");
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("改名按任务ID同步共享及我的缓存，不向其他用户范围插入任务", async () => {
  const original = { ...source[0], title: "旧名" };
  const another = { ...source[4], title: "旧名" };
  const values = new Map([
    [serverStateKeys.taskList(), [original, another]],
    [serverStateKeys.taskList("me"), [original]],
    [serverStateKeys.taskList("other"), [another]],
  ]);
  const mutate = vi.fn(async (match, update) => {
    for (const [key, data] of values) if (match(key)) values.set(key, update(data));
  });
  await refreshTaskNameState(mutate, { ...original, title: "新名" }, "旧名");
  const cached = [...values.values()];
  expect(cached[0].map((task) => task.title)).toEqual(["新名", "旧名"]);
  expect(cached[1][0].title).toBe("新名");
  expect(cached[2]).toEqual([another]);
});

test("我的任务改名和归档后的刷新继续使用当前ID查询", async () => {
  let state;
  function Probe() {
    const current = useTaskMonitorState({
      notify: vi.fn(),
      onNavigate: vi.fn(),
      onChanged: vi.fn(),
      listState: {
        filter: "all",
        owner: "all",
        ownerId: "me",
        query: "",
        sort: "updated_desc",
        attentionOnly: false,
      },
    });
    useEffect(() => {
      state = current;
    });
    return null;
  }
  api.archiveTasks.mockResolvedValue(undefined);
  render(<Probe />);
  await waitFor(() => expect(state.tasks.length).toBeGreaterThan(0));
  await act(() => state.onTaskRenamed({ ...source[0], title: "新名称" }));
  expect(api.tasks).toHaveBeenLastCalledWith({
    include_archived: true,
    owner_id: "me",
  });
  await act(() => state.archiveTasks(["mine-done"], true));
  expect(api.archiveTasks).toHaveBeenCalledWith(["mine-done"], true);
  expect(api.tasks).toHaveBeenLastCalledWith({
    include_archived: true,
    owner_id: "me",
  });
});

test("我的范围刷新失败后清除范围，共享列表成功不保留旧错误", async () => {
  let state;
  function Probe({ ownerId }) {
    const current = useTaskMonitorState({
      notify: vi.fn(),
      onNavigate: vi.fn(),
      onChanged: vi.fn(),
      listState: {
        filter: "active",
        owner: "all",
        ownerId,
        query: "",
        sort: "updated_desc",
        attentionOnly: false,
      },
    });
    useEffect(() => {
      state = current;
    });
    return null;
  }
  const view = render(<Probe ownerId="me" />);
  await waitFor(() => expect(state.tasks.length).toBeGreaterThan(0));
  api.tasks.mockRejectedValueOnce(new Error("我的范围刷新失败"));
  await act(() => state.loadTasks(true));
  expect(state.listError).toBe("我的范围刷新失败");
  view.rerender(<Probe ownerId={undefined} />);
  await waitFor(() =>
    expect(state.tasks.some((task) => task.id === "other-running")).toBe(true),
  );
  expect(state.listError).toBe("");
  expect(state.listRefreshError).toBe("");
  expect(api.tasks).toHaveBeenLastCalledWith({ include_archived: true });
});
test("当前ID请求隔离同名创建者，仅显示未结束且未归档任务，清除恢复共享列表", async () => {
  const user = userEvent.setup();
  render(<Harness />);
  await screen.findByRole("button", { name: "mine-running" });
  expect(api.tasks).toHaveBeenCalledWith({ include_archived: true, owner_id: "me" });
  expect(screen.getByRole("button", { name: "mine-queued" })).toBeVisible();
  expect(screen.getByRole("button", { name: "mine-paused" })).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "other-running" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "mine-done" })).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "mine-archived" }),
  ).not.toBeInTheDocument();
  expect(
    within(screen.getByRole("button", { name: "未结束", exact: true })).getByText("3"),
  ).toBeVisible();
  expect(screen.getByText("范围：我创建的任务")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "清除范围" }));
  await screen.findByRole("button", { name: "other-running" });
  expect(api.tasks).toHaveBeenLastCalledWith({ include_archived: true });
  expect(window.location.hash).not.toContain("scope=mine");
  expect(window.location.hash).toContain("status=active");
  expect(screen.queryByText("范围：我创建的任务")).not.toBeInTheDocument();
});
test("共享列表缓存不会污染我的任务范围，再进入范围仍按当前ID读", async () => {
  window.history.replaceState(null, "", "#analysis-tasks?status=active");
  const view = render(<Harness />);
  await screen.findByRole("button", { name: "other-running" });
  act(() => {
    window.history.replaceState(null, "", "#analysis-tasks?scope=mine&status=active");
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  await waitFor(() =>
    expect(api.tasks).toHaveBeenLastCalledWith({
      include_archived: true,
      owner_id: "me",
    }),
  );
  await screen.findByRole("button", { name: "mine-running" });
  expect(
    screen.queryByRole("button", { name: "other-running" }),
  ).not.toBeInTheDocument();
  view.unmount();
  render(<Harness />);
  await screen.findByRole("button", { name: "mine-running" });
  expect(api.tasks).toHaveBeenLastCalledWith({
    include_archived: true,
    owner_id: "me",
  });
});
