import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { renderWithServerState as render } from "./renderWithServerState";
import { mocks, item } from "./task-recycle-test-state";
import { TaskRuntimePage } from "../src/features/task-runtime/TaskRuntimePage";
import { useHashRoute, buildHash } from "../src/app/hashRouter";
import { recycleViewState } from "../src/features/task-runtime/useTaskRecycleView";

vi.mock("../src/features/task-runtime/TaskMonitor", () => ({
  TaskMonitor: ({ onReturnRecycle }) => (
    <div>
      <h1>合成任务详情</h1>
      {onReturnRecycle && (
        <button onClick={onReturnRecycle}>返回 Listing 回收站</button>
      )}
    </div>
  ),
}));
function Harness() {
  const { route } = useHashRoute();
  return (
    <TaskRuntimePage
      route={route}
      notify={vi.fn()}
      onNavigate={vi.fn()}
      onChanged={vi.fn()}
    />
  );
}
test("搜索分页地址可直接恢复，进入任务后明确返回并恢复滚动与原按钮焦点", async () => {
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  Object.defineProperty(window, "scrollY", { configurable: true, value: 560 });
  const destination = buildHash("analysis-tasks", {
    view: "recycle",
    q: "合成",
    page: 2,
    page_size: 50,
  });
  window.history.replaceState(null, "", destination);
  mocks.request.mockResolvedValue({ items: [item], total: 60 });
  render(<Harness />);
  const task = await screen.findByRole("button", { name: item.task_title });
  expect(screen.getByRole("textbox", { name: "搜索回收站" })).toHaveValue("合成");
  expect(
    within(screen.getByRole("group", { name: "回收站顶部分页" })).getByRole(
      "navigation",
    ),
  ).toHaveAttribute("aria-label", "分页，第 2 页，共 2 页");
  await userEvent.click(task);
  expect(
    new URLSearchParams(window.location.hash.split("?")[1]).get("recycle_return"),
  ).toBe(destination);
  await userEvent.click(
    await screen.findByRole("button", { name: "返回 Listing 回收站" }),
  );
  expect(window.location.hash).toBe(destination);
  const returned = await screen.findByRole("button", { name: item.task_title });
  await waitFor(() => expect(returned).toHaveFocus());
  expect(window.scrollTo).toHaveBeenLastCalledWith({
    top: 560,
    left: 0,
    behavior: "auto",
  });
  expect(mocks.control).not.toHaveBeenCalled();
  Object.defineProperty(window, "scrollY", { configurable: true, value: 0 });
  vi.restoreAllMocks();
});

test("搜索、数量和页码同步地址，刷新和清除保持正确范围", async () => {
  window.history.replaceState(null, "", "#analysis-tasks?view=recycle");
  mocks.request.mockResolvedValue({ items: [item], total: 60 });
  render(<Harness />);
  await userEvent.type(
    await screen.findByRole("textbox", { name: "搜索回收站" }),
    "SYNTHETIC{Enter}",
  );
  await waitFor(() => expect(window.location.hash).toContain("q=SYNTHETIC"));
  const top = within(screen.getByRole("group", { name: "回收站顶部分页" }));
  await userEvent.click(top.getByRole("combobox", { name: "每页数量" }));
  await userEvent.click(await screen.findByRole("option", { name: "50 条/页" }));
  await userEvent.click(top.getByRole("button", { name: "下一页" }));
  expect(window.location.hash).toContain("page=2");
  expect(window.location.hash).toContain("page_size=50");
  await userEvent.click(screen.getByRole("button", { name: "刷新回收站" }));
  expect(window.location.hash).toContain("page=2");
  await userEvent.click(screen.getByRole("button", { name: "清除搜索" }));
  expect(window.location.hash).not.toContain("q=");
  expect(window.location.hash).not.toContain("page=2");
  expect(window.location.hash).toContain("page_size=50");
});

test.each([
  "#classification-results?view=recycle",
  "https://invalid.example",
  "#analysis-tasks?view=other",
])("忽略不属于回收站的返回地址 %s", (target) => {
  window.history.replaceState(
    null,
    "",
    buildHash("analysis-tasks", { task_id: "task", recycle_return: target }),
  );
  render(<Harness />);
  expect(
    screen.queryByRole("button", { name: "返回 Listing 回收站" }),
  ).not.toBeInTheDocument();
});

test("回收站地址参数按既有页大小和合法页码规范化", () => {
  expect(recycleViewState({ page: "-2", page_size: "999", q: "合成" })).toEqual({
    page: 1,
    pageSize: 20,
    search: "合成",
  });
  expect(recycleViewState({ page: "3", page_size: "100" })).toEqual({
    page: 3,
    pageSize: 100,
    search: "",
  });
});
