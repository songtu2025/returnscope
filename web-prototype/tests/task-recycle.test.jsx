import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { renderWithServerState as render } from "./renderWithServerState";

const mocks = vi.hoisted(() => ({ request: vi.fn(), control: vi.fn() }));
vi.mock("../src/shared/api/request", () => ({ request: mocks.request }));
vi.mock("../src/shared/api/taskApi", () => ({
  taskApi: { controlTaskSegment: mocks.control },
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
