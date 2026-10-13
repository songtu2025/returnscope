import { beforeEach, afterEach, expect, test, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { renderWithServerState as render } from "./renderWithServerState";
const mocks = vi.hoisted(() => ({
  tasks: vi.fn(),
  task: vi.fn(),
  renameTask: vi.fn(),
  summary: vi.fn(),
  dataVersionReferences: vi.fn(),
}));
vi.mock("../src/api", () => ({ api: mocks }));
vi.mock("../src/shared/api/workbenchApi", () => ({
  workbenchApi: { summary: mocks.summary },
}));
import { TaskMonitor } from "../src/features/task-runtime/TaskMonitor";
import { WorkbenchPage } from "../src/features/workbench/WorkbenchPage";
import { DatasetReferences } from "../src/features/data-management/DatasetReferences";
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
}

test("列表直接改名刷新名称，取消不发请求", async () => {
  const { onNavigate } = await openRename();
  await userEvent.click(screen.getByRole("button", { name: "取消改名", exact: true }));
  expect(mocks.renameTask).not.toHaveBeenCalled();
  await userEvent.click(
    screen.getByRole("button", { name: "修改任务名称：合成原任务" }),
  );
  await fillName();
  const updated = { ...original, title: "合成新任务", revision: 2 };
  mocks.renameTask.mockResolvedValue(updated);
  mocks.tasks.mockResolvedValue([updated]);
  await userEvent.click(screen.getByRole("button", { name: "保存名称" }));
  await waitFor(() => expect(screen.queryByLabelText("任务名称")).toBeNull());
  expect(screen.getByText("合成新任务")).toBeVisible();
  expect(mocks.renameTask).toHaveBeenCalledWith(original.id, {
    title: "合成新任务",
    expected_revision: 1,
  });
  expect(onNavigate).not.toHaveBeenCalled();
});

test("保存失败和冲突保留名称输入，获取最新修订后可以再次提交", async () => {
  await openRename();
  await fillName();
  mocks.renameTask.mockRejectedValueOnce(new Error("合成保存失败"));
  await userEvent.click(screen.getByRole("button", { name: "保存名称" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("合成保存失败");
  expect(screen.getByLabelText("任务名称")).toHaveValue("合成新任务");
  mocks.renameTask.mockRejectedValueOnce(
    Object.assign(new Error("合成修订冲突"), { status: 409 }),
  );
  mocks.task.mockResolvedValue({ ...original, revision: 2 });
  await userEvent.click(screen.getByRole("button", { name: "保存名称" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("合成修订冲突");
  expect(screen.getByLabelText("任务名称")).toHaveValue("合成新任务");
  const updated = { ...original, title: "合成新任务", revision: 3 };
  mocks.renameTask.mockResolvedValue(updated);
  mocks.tasks.mockResolvedValue([updated]);
  await userEvent.click(screen.getByRole("button", { name: "保存名称" }));
  await waitFor(() => expect(screen.queryByLabelText("任务名称")).toBeNull());
  expect(mocks.renameTask).toHaveBeenLastCalledWith(original.id, {
    title: "合成新任务",
    expected_revision: 2,
  });
});

test("同名任务按 ID 独立修改，空名称不提交且 Escape 取消", async () => {
  const second = { ...original, id: "synthetic-second" };
  mocks.tasks.mockResolvedValue([original, second]);
  render(<TaskMonitor notify={vi.fn()} onNavigate={vi.fn()} />);
  const edits = await screen.findAllByRole("button", {
    name: "修改任务名称：合成原任务",
  });
  await userEvent.click(edits[0]);
  await userEvent.clear(screen.getByLabelText("任务名称"));
  expect(screen.getByRole("button", { name: "保存名称" })).toBeDisabled();
  await userEvent.keyboard("{Escape}");
  expect(mocks.renameTask).not.toHaveBeenCalled();
  await userEvent.click(
    screen.getAllByRole("button", { name: "修改任务名称：合成原任务" })[0],
  );
  const updated = { ...original, title: "合成新任务", revision: 2 };
  mocks.renameTask.mockResolvedValue(updated);
  mocks.tasks.mockResolvedValue([updated, second]);
  await fillName();
  await userEvent.keyboard("{Enter}");
  await screen.findByText("合成新任务");
  expect(screen.getByText("合成原任务")).toBeVisible();
  expect(mocks.renameTask).toHaveBeenCalledWith(original.id, {
    title: "合成新任务",
    expected_revision: 1,
  });
});

function RenameJourney() {
  const [view, setView] = useState("home");
  const [page, setPage] = useState(1);
  return (
    <>
      <button onClick={() => setView("home")}>验收首页</button>
      <button onClick={() => setView("tasks")}>验收任务</button>
      <button
        onClick={() => {
          setPage(1);
          setView("references");
        }}
      >
        验收引用第一页
      </button>
      <button
        onClick={() => {
          setPage(2);
          setView("references");
        }}
      >
        验收引用第二页
      </button>
      {view === "home" && <WorkbenchPage onNavigate={vi.fn()} />}
      {view === "tasks" && <TaskMonitor notify={vi.fn()} onNavigate={vi.fn()} />}
      {view === "references" && (
        <DatasetReferences currentVersionId="synthetic-products" page={page} />
      )}
    </>
  );
}

test("改名后立即切回首页和引用各页，慢请求期间缓存已是新名称且同名任务不受影响", async () => {
  const action = {
    type: "paused",
    object_type: "task",
    object_id: original.id,
    title: original.title,
    target: { task_id: original.id },
  };
  mocks.summary.mockResolvedValueOnce({
    actions: [
      action,
      { ...action, object_id: "second", target: { task_id: "second" } },
      {
        ...action,
        object_type: "task_segment",
        object_id: "segment",
        title: `${original.title} / L1`,
      },
    ],
    recent_outputs: [],
    counts: {},
  });
  mocks.dataVersionReferences.mockImplementation(async (_id, { page }) => ({
    items: [
      { task_id: original.id, title: original.title, reference_type: "products" },
      { task_id: "second", title: original.title, reference_type: "products" },
    ],
    total: 21,
    page,
  }));
  render(<RenameJourney />);
  await screen.findByText(`${original.title} / L1`);
  await userEvent.click(screen.getByRole("button", { name: "验收引用第一页" }));
  await screen.findByRole("table", { name: "任务引用列表" });
  await userEvent.click(screen.getByRole("button", { name: "验收引用第二页" }));
  await screen.findByText("共 21 条 · 第 2/2 页");
  await userEvent.click(screen.getByRole("button", { name: "验收任务" }));
  await userEvent.click(
    await screen.findByRole("button", { name: "修改任务名称：合成原任务" }),
  );
  await fillName();
  const updated = { ...original, title: "合成新任务", revision: 2 };
  mocks.renameTask.mockResolvedValue(updated);
  mocks.tasks.mockResolvedValue([updated]);
  await userEvent.click(screen.getByRole("button", { name: "保存名称" }));
  await screen.findByRole("button", { name: "修改任务名称：合成新任务" });
  // 切换后故意不完成读取，验证新名称来自已同步缓存。
  mocks.summary.mockImplementation(() => new Promise(() => {}));
  mocks.dataVersionReferences.mockImplementation(() => new Promise(() => {}));
  await userEvent.click(screen.getByRole("button", { name: "验收首页" }));
  expect(screen.getByText("合成新任务")).toBeVisible();
  expect(screen.getByText("合成新任务 / L1")).toBeVisible();
  expect(screen.getByText("合成原任务")).toBeVisible();
  for (const label of ["验收引用第一页", "验收引用第二页"]) {
    await userEvent.click(screen.getByRole("button", { name: label }));
    expect(screen.getByText("合成新任务")).toBeVisible();
    expect(screen.getByText("合成原任务")).toBeVisible();
  }
});
