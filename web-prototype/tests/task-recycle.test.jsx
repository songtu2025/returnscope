import {
  act,
  cleanup,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { renderWithServerState as render } from "./renderWithServerState";

const mocks = vi.hoisted(() => ({
  request: vi.fn(),
  control: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("../src/shared/api/request", () => ({ request: mocks.request }));
vi.mock("../src/shared/api/taskApi", () => ({
  taskApi: { controlTaskSegment: mocks.control },
}));
vi.mock("../src/shared/serverState", async (load) => ({
  ...(await load()),
  refreshServerState: mocks.refresh,
}));
import { TaskRecyclePage } from "../src/features/task-runtime/TaskRecyclePage";

const item = {
  id: "synthetic-segment",
  task_id: "synthetic-task",
  segment_key: "synthetic-key",
  task_revision: 3,
  task_title: "合成验收任务",
  scope: { listing: "SYNTHETIC", store: "合成站点" },
  removed_by: "合成用户",
  deleted_at: "2026-10-14T00:00:00Z",
};
beforeEach(() => {
  vi.resetAllMocks();
  mocks.request.mockResolvedValue({ items: [item], total: 1 });
  mocks.control.mockResolvedValue({});
  mocks.refresh.mockResolvedValue(undefined);
});
afterEach(cleanup);

test("回收站恢复只提交恢复动作，带任务修订号并刷新列表", async () => {
  const notify = vi.fn();
  render(<TaskRecyclePage notify={notify} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "恢复", exact: true }),
  );
  expect(mocks.control).toHaveBeenCalledExactlyOnceWith(
    "synthetic-task",
    "synthetic-key",
    "restore",
    { expected_revision: 3 },
  );
  expect(notify).toHaveBeenCalledWith("Listing 已恢复，不会自动执行");
  await waitFor(() => expect(mocks.request).toHaveBeenCalledTimes(2));
});

test("永久删除必须确认，提交期间不可重复操作", async () => {
  let finish;
  mocks.control.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  render(<TaskRecyclePage notify={vi.fn()} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "永久删除", exact: true }),
  );
  expect(screen.getByRole("dialog")).toHaveTextContent(
    "已有分类结果、看板和必要来源信息保留",
  );
  expect(mocks.control).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "确认永久删除" }));
  expect(screen.getByRole("button", { name: "正在删除…" })).toBeDisabled();
  expect(mocks.control).toHaveBeenCalledExactlyOnceWith(
    "synthetic-task",
    "synthetic-key",
    "purge",
    { expected_revision: 3 },
  );
  finish({});
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

test("版本冲突保留记录并刷新修订号，搜索提交后生效", async () => {
  mocks.control.mockRejectedValue(new Error("任务已更新"));
  const notify = vi.fn();
  render(<TaskRecyclePage notify={notify} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "恢复", exact: true }),
  );
  expect(notify).toHaveBeenCalledWith("任务已更新", "error");
  expect(screen.getByText("SYNTHETIC")).toBeVisible();
  await userEvent.type(screen.getByRole("textbox", { name: "搜索回收站" }), "不存在");
  await userEvent.click(screen.getByRole("button", { name: "搜索", exact: true }));
  await waitFor(() =>
    expect(mocks.request).toHaveBeenCalledWith(
      expect.stringContaining(encodeURIComponent("不存在")),
    ),
  );
});

test("恢复成功后可定位所属任务和 Listing，不触发执行", async () => {
  window.location.hash = "#task-recycle";
  const notify = vi.fn();
  render(<TaskRecyclePage notify={notify} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "恢复", exact: true }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "SYNTHETIC 已恢复，不会自动执行",
  );
  await userEvent.click(screen.getByRole("button", { name: "查看所属任务" }));
  const query = new URLSearchParams(window.location.hash.split("?")[1]);
  expect(window.location.hash).toContain("#analysis-tasks?");
  expect(query.get("task_id")).toBe(item.task_id);
  expect(query.get("segment_id")).toBe(item.id);
  expect(mocks.control).toHaveBeenCalledTimes(1);
  expect(mocks.control.mock.lastCall[2]).toBe("restore");
});

test("恢复已成功但刷新失败时保留入口和剩余列表，解除忙态后可以重试", async () => {
  const other = {
    ...item,
    id: "second-segment",
    scope: { listing: "SECOND", store: "合成站点" },
  };
  mocks.request
    .mockResolvedValueOnce({ items: [item, other], total: 2 })
    .mockRejectedValueOnce(new Error("刷新失败"))
    .mockResolvedValue({ items: [other], total: 1 });
  const notify = vi.fn();
  render(<TaskRecyclePage notify={notify} />);
  const firstRow = (await screen.findByText("SYNTHETIC")).closest("tr");
  await userEvent.click(
    within(firstRow).getByRole("button", { name: "恢复", exact: true }),
  );
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("列表刷新失败"),
  );
  expect(screen.getByRole("button", { name: "查看所属任务" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "恢复", exact: true })).toBeEnabled();
  expect(screen.getByText("SECOND")).toBeVisible();
  expect(screen.queryByText("SYNTHETIC", { selector: "b" })).not.toBeInTheDocument();
  expect(notify).toHaveBeenCalledWith("Listing 已恢复，不会自动执行");
  expect(notify).not.toHaveBeenCalledWith("刷新失败", "error");
  await userEvent.click(screen.getByRole("button", { name: "重试刷新" }));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  expect(mocks.request).toHaveBeenCalledTimes(3);
  expect(mocks.control).toHaveBeenCalledTimes(1);
});

test("服务端失败并遇到刷新失败仍解除忙态，不能显示恢复成功", async () => {
  mocks.control.mockRejectedValueOnce(new Error("恢复被拒绝"));
  mocks.request
    .mockResolvedValueOnce({ items: [item], total: 1 })
    .mockRejectedValueOnce(new Error("刷新失败"));
  const notify = vi.fn();
  render(<TaskRecyclePage notify={notify} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "恢复", exact: true }),
  );
  await screen.findByRole("alert");
  expect(notify).toHaveBeenCalledWith("恢复被拒绝", "error");
  expect(
    screen.queryByRole("button", { name: "查看所属任务" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "恢复", exact: true })).toBeEnabled();
});

test("第二页最后一项恢复后自动回落第一页，重复操作不被旧busy锁住", async () => {
  mocks.request.mockImplementation(async (url) => {
    if (url.includes("page=2"))
      return { items: [item], total: mocks.control.mock.calls.length ? 20 : 21 };
    return {
      items: Array.from({ length: 20 }, (_, i) => ({
        ...item,
        id: `first-${i}`,
        scope: { listing: `FIRST-${i}` },
      })),
      total: mocks.control.mock.calls.length ? 20 : 21,
    };
  });
  render(<TaskRecyclePage notify={vi.fn()} />);
  await screen.findByText("FIRST-0");
  await userEvent.click(screen.getByRole("button", { name: "下一页" }));
  await screen.findByText("SYNTHETIC");
  await userEvent.click(screen.getByRole("button", { name: "恢复", exact: true }));
  await waitFor(() => expect(screen.getByText("共 20 条 · 第 1 页")).toBeVisible());
  expect(await screen.findByText("FIRST-0")).toBeVisible();
  expect(screen.getAllByRole("button", { name: "恢复", exact: true })[0]).toBeEnabled();
});

test("关联模块刷新失败不误报恢复失败，也不阻断回收站刷新", async () => {
  mocks.refresh.mockRejectedValueOnce(new Error("关联模块刷新失败"));
  mocks.request
    .mockResolvedValueOnce({ items: [item], total: 1 })
    .mockResolvedValue({ items: [], total: 0 });
  const notify = vi.fn();
  render(<TaskRecyclePage notify={notify} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "恢复", exact: true }),
  );
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("列表刷新失败"),
  );
  expect(screen.getByRole("button", { name: "重试刷新" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "查看所属任务" })).toBeEnabled();
  expect(mocks.request).toHaveBeenCalledTimes(2);
  expect(notify).toHaveBeenCalledWith("Listing 已恢复，不会自动执行");
  expect(notify).not.toHaveBeenCalledWith("关联模块刷新失败", "error");
});

test("恢复期间保留搜索输入但锁定提交和分页，结束后可以操作", async () => {
  let finish;
  mocks.control.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  mocks.request.mockResolvedValue({ items: [item], total: 41 });
  render(<TaskRecyclePage notify={vi.fn()} />);
  await screen.findByText("SYNTHETIC");
  await userEvent.click(screen.getByRole("button", { name: "下一页" }));
  await screen.findByText("共 41 条 · 第 2 页");
  await userEvent.click(screen.getByRole("button", { name: "恢复", exact: true }));
  const input = screen.getByRole("textbox", { name: "搜索回收站" });
  await userEvent.type(input, "新范围{Enter}");
  fireEvent.submit(input.closest("form"));
  expect(input).toHaveValue("新范围");
  for (const name of ["搜索", "上一页", "下一页"])
    expect(screen.getByRole("button", { name, exact: true })).toBeDisabled();
  expect(screen.getByText("共 41 条 · 第 2 页")).toBeVisible();
  expect(mocks.request).toHaveBeenCalledTimes(2);
  await act(async () => finish({}));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "搜索", exact: true })).toBeEnabled(),
  );
  await userEvent.click(screen.getByRole("button", { name: "上一页" }));
  await screen.findByText("共 41 条 · 第 1 页");
  await userEvent.click(screen.getByRole("button", { name: "下一页" }));
  await screen.findByText("共 41 条 · 第 2 页");
  await userEvent.click(screen.getByRole("button", { name: "搜索", exact: true }));
  await waitFor(() =>
    expect(mocks.request).toHaveBeenCalledWith(
      `/api/tasks/recycle?q=${encodeURIComponent("新范围")}&page=1`,
    ),
  );
});
