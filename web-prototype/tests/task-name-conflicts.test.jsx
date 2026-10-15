import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TaskNameEditor } from "../src/features/task-runtime/TaskNameEditor";
import { renderWithServerState as render } from "./renderWithServerState";

const api = vi.hoisted(() => ({ renameTask: vi.fn(), task: vi.fn() }));
vi.mock("../src/api", () => ({ api }));
const task = {
  id: "synthetic",
  title: "原任务",
  revision: 1,
  status: "completed",
  segments: [],
};
const conflict = () => Object.assign(new Error("冲突"), { status: 409 });
beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);
async function start() {
  const onSaved = vi.fn().mockResolvedValue(undefined);
  render(<TaskNameEditor task={task} onSaved={onSaved} />);
  await userEvent.click(screen.getByRole("button", { name: "修改任务名称：原任务" }));
  await userEvent.clear(screen.getByRole("textbox", { name: "任务名称" }));
  await userEvent.type(screen.getByRole("textbox", { name: "任务名称" }), "我的名称");
  api.renameTask.mockRejectedValueOnce(conflict());
  await userEvent.click(screen.getByRole("button", { name: "保存名称" }));
  return onSaved;
}

test("冲突保留草稿并展示最新名称，采用最新只同步不再请求改名", async () => {
  const latest = { ...task, title: "他人名称", revision: 2 };
  api.task.mockResolvedValue(latest);
  const onSaved = await start();
  expect(screen.getByRole("region", { name: "任务名称冲突核对" })).toHaveTextContent(
    "最新名称他人名称我的名称我的名称",
  );
  expect(screen.getByLabelText("任务名称")).toHaveValue("我的名称");
  expect(screen.getByRole("button", { name: "保存名称" })).toBeDisabled();
  await userEvent.keyboard("{Enter}");
  expect(api.renameTask).toHaveBeenCalledTimes(1);
  await userEvent.click(screen.getByRole("button", { name: "采用最新名称" }));
  expect(onSaved).toHaveBeenCalledExactlyOnceWith(latest);
  expect(api.renameTask).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("textbox", { name: "任务名称" })).not.toBeInTheDocument();
});

test("二次409再次要求核对，回填原名称也使用最新CAS不被旧名称短路", async () => {
  api.task
    .mockResolvedValueOnce({ ...task, title: "他人名称", revision: 2 })
    .mockResolvedValueOnce({ ...task, title: "再次改名", revision: 3 });
  await start();
  await userEvent.clear(screen.getByLabelText("任务名称"));
  await userEvent.type(screen.getByLabelText("任务名称"), "原任务");
  await userEvent.click(screen.getByRole("button", { name: "采用我的名称" }));
  api.renameTask.mockRejectedValueOnce(conflict());
  await userEvent.click(screen.getByRole("button", { name: "保存名称" }));
  expect(api.renameTask).toHaveBeenLastCalledWith(task.id, {
    title: "原任务",
    expected_revision: 2,
  });
  expect(screen.getByRole("region", { name: "任务名称冲突核对" })).toHaveTextContent(
    "再次改名",
  );
  expect(screen.getByRole("button", { name: "保存名称" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "采用我的名称" }));
  api.renameTask.mockResolvedValue({ ...task, revision: 4 });
  await userEvent.click(screen.getByRole("button", { name: "保存名称" }));
  expect(api.renameTask).toHaveBeenLastCalledWith(task.id, {
    title: "原任务",
    expected_revision: 3,
  });
});

test("实际最新名称已相同则明确提示，无需再次保存", async () => {
  const latest = { ...task, title: "我的名称", revision: 2 };
  api.task.mockResolvedValue(latest);
  const onSaved = await start();
  expect(screen.getByRole("status")).toHaveTextContent("无需再次保存");
  expect(
    screen.queryByRole("button", { name: "采用我的名称" }),
  ).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "采用最新名称" }));
  expect(onSaved).toHaveBeenCalledWith(latest);
  expect(api.renameTask).toHaveBeenCalledTimes(1);
});

test("读取最新失败保留草稿与提交锁定，重试成功后明确选择", async () => {
  api.task
    .mockRejectedValueOnce(new Error("读取失败"))
    .mockResolvedValueOnce({ ...task, title: "最新名称", revision: 2 });
  await start();
  expect(screen.getByRole("alert")).toHaveTextContent("输入已保留");
  expect(screen.getByLabelText("任务名称")).toHaveValue("我的名称");
  expect(screen.getByRole("button", { name: "保存名称" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "重新读取任务" }));
  await waitFor(() =>
    expect(screen.getByText("最新名称", { selector: "dd" })).toBeVisible(),
  );
  expect(api.renameTask).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "保存名称" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "取消改名" }));
  expect(screen.queryByRole("textbox", { name: "任务名称" })).not.toBeInTheDocument();
});
