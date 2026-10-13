import { beforeEach, afterEach, expect, test, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithServerState as render } from "./renderWithServerState";
const mocks = vi.hoisted(() => ({
  tasks: vi.fn(),
  task: vi.fn(),
  renameTask: vi.fn(),
}));
vi.mock("../src/api", () => ({ api: mocks }));
import { TaskMonitor } from "../src/features/task-runtime/TaskMonitor";
const original = {
  id: "synthetic-task",
  title: "合成原任务",
  revision: 1,
  status: "completed",
  segments: [],
  owner_name: "合成用户",
};
beforeEach(() => {
  vi.resetAllMocks();
  mocks.tasks.mockResolvedValue([original]);
});
afterEach(cleanup);

async function openRename() {
  const onNavigate = vi.fn();
  const notify = vi.fn();
  render(<TaskMonitor notify={notify} onNavigate={onNavigate} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "修改任务名称：合成原任务" }),
  );
  expect(onNavigate).not.toHaveBeenCalled();
  return { notify, onNavigate };
}
async function fillName() {
  await userEvent.clear(screen.getByLabelText("任务名称"));
  await userEvent.type(screen.getByLabelText("任务名称"), "合成新任务");
  await userEvent.type(screen.getByLabelText("修改原因"), "合成修改原因");
}

test("列表直接改名刷新名称，取消不发请求", async () => {
  const { onNavigate } = await openRename();
  await userEvent.click(screen.getByRole("button", { name: "取消", exact: true }));
  expect(mocks.renameTask).not.toHaveBeenCalled();
  await userEvent.click(
    screen.getByRole("button", { name: "修改任务名称：合成原任务" }),
  );
  await fillName();
  const updated = { ...original, title: "合成新任务", revision: 2 };
  mocks.renameTask.mockResolvedValue(updated);
  mocks.tasks.mockResolvedValue([updated]);
  await userEvent.click(screen.getByRole("button", { name: "保存修改" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(screen.getByText("合成新任务")).toBeVisible();
  expect(mocks.renameTask).toHaveBeenCalledWith(original.id, {
    title: "合成新任务",
    note: "合成修改原因",
    expected_revision: 1,
  });
  expect(onNavigate).not.toHaveBeenCalled();
});

test("保存失败和冲突保留名称输入，获取最新修订后可以再次提交", async () => {
  const { notify } = await openRename();
  await fillName();
  mocks.renameTask.mockRejectedValueOnce(new Error("合成保存失败"));
  await userEvent.click(screen.getByRole("button", { name: "保存修改" }));
  await waitFor(() => expect(notify).toHaveBeenCalledWith("合成保存失败", "error"));
  expect(screen.getByLabelText("任务名称")).toHaveValue("合成新任务");
  mocks.renameTask.mockRejectedValueOnce(
    Object.assign(new Error("合成修订冲突"), { status: 409 }),
  );
  mocks.task.mockResolvedValue({ ...original, revision: 2 });
  await userEvent.click(screen.getByRole("button", { name: "保存修改" }));
  await waitFor(() => expect(notify).toHaveBeenCalledWith("合成修订冲突", "error"));
  expect(screen.getByLabelText("任务名称")).toHaveValue("合成新任务");
  const updated = { ...original, title: "合成新任务", revision: 3 };
  mocks.renameTask.mockResolvedValue(updated);
  mocks.tasks.mockResolvedValue([updated]);
  await userEvent.click(screen.getByRole("button", { name: "保存修改" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(mocks.renameTask).toHaveBeenLastCalledWith(original.id, {
    title: "合成新任务",
    note: "合成修改原因",
    expected_revision: 2,
  });
});
