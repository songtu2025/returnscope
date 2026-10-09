import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { TaskRegistry } from "../src/features/task-runtime/TaskRegistry";
import { renderWithServerState as render } from "./renderWithServerState";

afterEach(cleanup);

function task(id, status = "completed", changes = {}) {
  return {
    id,
    title: `SYNTHETIC ${id}`,
    status,
    owner_name: "合成甲",
    store: "合成站点",
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-02T00:00:00Z",
    progress_percent: 50,
    progress_current: 5,
    progress_total: 10,
    segments: [],
    ...changes,
  };
}

function setup(options = {}) {
  const props = {
    tasks: [task("a"), task("b"), task("running", "running")],
    selectedId: null,
    viewState: {
      filter: "all",
      query: "",
      owner: "all",
      sort: "updated_desc",
      attentionOnly: false,
    },
    onViewStateChange: vi.fn(),
    loading: false,
    error: "",
    hasData: true,
    onReload: vi.fn(),
    onCreate: vi.fn(),
    onOpen: vi.fn(),
    onArchive: vi.fn().mockResolvedValue(true),
    onCreateSimilar: vi.fn(),
    ...options,
  };
  return { props, ...render(<TaskRegistry {...props} />) };
}

function rowTitles() {
  return [...document.querySelectorAll(".task-registry-identity b")].map(
    (node) => node.textContent,
  );
}

test("状态分组计数包含归档，默认列表只显示未归档且运行任务不能选择", () => {
  setup({
    tasks: [
      task("done"),
      task("live", "paused"),
      task("archive", "failed", { archived_at: "2026-10-03" }),
    ],
  });
  expect(rowTitles()).toEqual(["SYNTHETIC done", "SYNTHETIC live"]);
  for (const [name, count] of [
    ["全部", 2],
    ["未结束", 1],
    ["已结束", 1],
    ["已归档", 1],
  ])
    expect(screen.getByRole("button", { name, exact: true })).toHaveTextContent(
      String(count),
    );
  expect(
    screen.getByRole("checkbox", { name: "选择任务：SYNTHETIC live" }),
  ).toBeDisabled();
});

test("搜索按原字段匹配并去除两端空格和大小写差异", () => {
  const { props, rerender } = setup({
    tasks: [
      task("a", "completed", { listing_search_text: "SYNTHETIC-LISTING" }),
      task("b"),
    ],
  });
  rerender(
    <TaskRegistry
      {...props}
      viewState={{ ...props.viewState, query: "  synthetic-listing  " }}
    />,
  );
  expect(rowTitles()).toEqual(["SYNTHETIC a"]);
});

test("负责人和需处理筛选组合沿用任务摘要判断", () => {
  const { props, rerender } = setup({
    tasks: [
      task("a", "partial"),
      task("b"),
      task("other", "failed", { owner_name: "合成乙" }),
    ],
  });
  rerender(
    <TaskRegistry
      {...props}
      viewState={{ ...props.viewState, owner: "合成甲", attentionOnly: true }}
    />,
  );
  expect(rowTitles()).toEqual(["SYNTHETIC a"]);
});

test.each([
  ["updated_desc", ["SYNTHETIC b", "SYNTHETIC a"]],
  ["created_desc", ["SYNTHETIC a", "SYNTHETIC b"]],
  ["progress_desc", ["SYNTHETIC b", "SYNTHETIC a"]],
])("排序%s保持对应字段顺序", (sort, expected) => {
  setup({
    tasks: [
      task("a", "completed", {
        created_at: "2026-10-03",
        updated_at: "2026-10-04",
        progress_percent: 10,
      }),
      task("b", "completed", {
        created_at: "2026-10-01",
        updated_at: "2026-10-05",
        progress_percent: 90,
      }),
    ],
    viewState: { filter: "all", query: "", owner: "all", sort, attentionOnly: false },
  });
  expect(rowTitles()).toEqual(expected);
});

test("筛选控件提交原字段，清空搜索后焦点返回输入", async () => {
  const user = userEvent.setup();
  const { props } = setup({
    viewState: {
      filter: "all",
      query: "SYNTHETIC",
      owner: "all",
      sort: "updated_desc",
      attentionOnly: false,
    },
  });
  await user.click(screen.getByRole("button", { name: "清空搜索" }));
  expect(props.onViewStateChange).toHaveBeenLastCalledWith({ query: "" });
  expect(
    screen.getByRole("textbox", { name: "搜索任务、店铺或 Listing" }),
  ).toHaveFocus();
  fireEvent.change(screen.getByRole("combobox", { name: "按负责人筛选" }), {
    target: { value: "合成甲" },
  });
  expect(props.onViewStateChange).toHaveBeenLastCalledWith({ owner: "合成甲" });
  fireEvent.change(screen.getByRole("combobox", { name: "任务排序" }), {
    target: { value: "created_desc" },
  });
  expect(props.onViewStateChange).toHaveBeenLastCalledWith({ sort: "created_desc" });
  await user.click(screen.getByRole("checkbox", { name: "只看需处理" }));
  expect(props.onViewStateChange).toHaveBeenLastCalledWith({ attentionOnly: true });
  await user.click(screen.getByRole("button", { name: "已结束", exact: true }));
  expect(props.onViewStateChange).toHaveBeenLastCalledWith({ filter: "finished" });
});

test("全选只包含可管理任务，保存中禁用操作，成功后清空选择", async () => {
  let finish;
  const onArchive = vi.fn(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  setup({ onArchive });
  const user = userEvent.setup();
  const selectAll = screen.getByRole("checkbox", {
    name: "选择当前列表中的可管理任务",
  });
  await user.click(screen.getByRole("checkbox", { name: "选择任务：SYNTHETIC a" }));
  expect(selectAll.indeterminate).toBe(true);
  await user.click(selectAll);
  expect(selectAll).toBeChecked();
  const batch = screen.getByRole("region", { name: "批量任务操作" });
  await user.click(within(batch).getByRole("button", { name: "归档", exact: true }));
  expect(onArchive).toHaveBeenCalledExactlyOnceWith(["a", "b"], true);
  expect(within(batch).getByRole("button", { name: "取消选择" })).toBeDisabled();
  expect(
    screen.getByRole("checkbox", { name: "选择任务：SYNTHETIC a" }),
  ).toBeDisabled();
  finish(true);
  await waitFor(() =>
    expect(screen.queryByRole("region", { name: "批量任务操作" })).toBeNull(),
  );
});

test("归档返回失败时保留选择，数据删除修剪选择，切换分组清空选择", async () => {
  const { props, rerender } = setup({ onArchive: vi.fn().mockResolvedValue(false) });
  const user = userEvent.setup();
  await user.click(
    screen.getByRole("checkbox", { name: "选择当前列表中的可管理任务" }),
  );
  await user.click(
    within(screen.getByRole("region", { name: "批量任务操作" })).getByRole("button", {
      name: "归档",
      exact: true,
    }),
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "取消选择" })).toBeEnabled(),
  );
  expect(screen.getByRole("region", { name: "批量任务操作" })).toHaveTextContent(
    "已选择 2 个任务",
  );
  rerender(<TaskRegistry {...props} tasks={[props.tasks[0]]} />);
  expect(screen.getByRole("region", { name: "批量任务操作" })).toHaveTextContent(
    "已选择 1 个任务",
  );
  rerender(
    <TaskRegistry {...props} viewState={{ ...props.viewState, filter: "finished" }} />,
  );
  expect(screen.queryByRole("region", { name: "批量任务操作" })).toBeNull();
});

test("归档分组恢复传false，查看和创建类似任务传原对象", async () => {
  const archived = task("archive", "completed", { archived_at: "2026-10-03" });
  const { props } = setup({
    tasks: [archived],
    selectedId: archived.id,
    viewState: {
      filter: "archived",
      query: "",
      owner: "all",
      sort: "updated_desc",
      attentionOnly: false,
    },
  });
  const user = userEvent.setup();
  expect(screen.getByRole("row", { name: /SYNTHETIC archive/ })).toHaveAttribute(
    "aria-current",
    "true",
  );
  await user.click(screen.getByRole("button", { name: "查看", exact: true }));
  expect(props.onOpen).toHaveBeenCalledExactlyOnceWith(archived);
  fireEvent.click(screen.getByLabelText("更多任务操作：SYNTHETIC archive"));
  await user.click(screen.getByRole("button", { name: "创建类似任务" }));
  expect(props.onCreateSimilar).toHaveBeenCalledExactlyOnceWith(archived);
  expect(screen.getByLabelText("更多任务操作：SYNTHETIC archive")).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  await user.click(screen.getByLabelText("更多任务操作：SYNTHETIC archive"));
  await user.click(screen.getByRole("button", { name: "恢复任务" }));
  expect(props.onArchive).toHaveBeenCalledExactlyOnceWith([archived.id], false);
});

test("加载、首次错误、过期数据和空列表保持原反馈及重试入口", async () => {
  const { props, rerender } = setup({ loading: true });
  expect(screen.getByText("读取任务…")).toBeVisible();
  expect(screen.queryByRole("table")).toBeNull();
  rerender(
    <TaskRegistry {...props} loading={false} error="合成失败" hasData={false} />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("任务列表读取失败");
  expect(screen.queryByRole("table")).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "重新加载" }));
  expect(props.onReload).toHaveBeenCalledOnce();
  rerender(<TaskRegistry {...props} loading={false} error="合成失败" hasData />);
  expect(screen.getByRole("alert")).toHaveTextContent("当前显示上一次数据");
  expect(screen.getByRole("table", { name: "任务管理表" })).toBeVisible();
  rerender(<TaskRegistry {...props} loading={false} tasks={[]} />);
  await userEvent.click(screen.getByRole("button", { name: "创建分析任务" }));
  expect(props.onCreate).toHaveBeenCalledOnce();
});
