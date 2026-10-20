import { useState } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test } from "vitest";
import { TaskDetailViews } from "../src/features/task-runtime/TaskDetailViews";

afterEach(cleanup);

const task = {
  id: "synthetic-task",
  status: "completed",
  segments: [{ id: "segment-a", segment_key: "key-a", scope: { listing: "DEMO" } }],
};
const events = Array.from({ length: 205 }, (_, index) => ({
  id: String(index),
  created_at: "2026-10-01T00:00:00Z",
  stage: "Listing 分类",
  event_type: "segment_progress",
  message: `合成进度 ${index}`,
  data: { segment_id: "segment-a" },
}));

function Execution() {
  const [query, setQuery] = useState("");
  return (
    <input
      aria-label="合成 Listing 查询"
      value={query}
      onChange={(event) => setQuery(event.target.value)}
    />
  );
}

function view(activeTab, fields = {}) {
  return (
    <TaskDetailViews
      key={fields.task?.id || task.id}
      task={task}
      events={events}
      executableSegments={[]}
      focusListing={null}
      activeTab={activeTab}
      execution={<Execution />}
      {...fields}
    />
  );
}

test("日志组合条件和已加载范围在页签往返中保留，隐藏页签不可访问", async () => {
  const user = userEvent.setup();
  const { rerender } = render(view("execution"));
  await user.type(screen.getByRole("textbox", { name: "合成 Listing 查询" }), "DEMO");
  expect(screen.queryByRole("searchbox")).toBeNull();
  rerender(view("events"));
  expect(screen.queryByRole("textbox", { name: "合成 Listing 查询" })).toBeNull();
  await user.selectOptions(
    screen.getByRole("combobox", { name: "日志 Listing" }),
    "key-a",
  );
  await user.selectOptions(
    screen.getByRole("combobox", { name: "日志事件类型" }),
    "segment_progress",
  );
  await user.type(screen.getByRole("searchbox"), "合成进度");
  await user.click(
    screen.getByRole("button", { name: "加载更早日志（已显示 100 / 205 条）" }),
  );
  rerender(view("config"));
  expect(screen.queryByRole("searchbox")).toBeNull();
  rerender(view("execution"));
  expect(screen.getByRole("textbox", { name: "合成 Listing 查询" })).toHaveValue(
    "DEMO",
  );
  rerender(view("events"));
  expect(screen.getByRole("searchbox")).toHaveValue("合成进度");
  expect(screen.getByRole("combobox", { name: "日志 Listing" })).toHaveValue("key-a");
  expect(screen.getByRole("combobox", { name: "日志事件类型" })).toHaveValue(
    "segment_progress",
  );
  expect(
    screen.getByRole("button", { name: "加载更早日志（已显示 200 / 205 条）" }),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "重置日志筛选" }));
  expect(screen.getByRole("searchbox")).toHaveValue("");
  expect(
    screen.getByRole("button", { name: "加载更早日志（已显示 100 / 205 条）" }),
  ).toBeVisible();
});

test("按任务标识重新挂载后不沿用前一个任务的日志条件", async () => {
  const { rerender } = render(view("events"));
  await userEvent.type(screen.getByRole("searchbox"), "前任务条件");
  rerender(view("events", { task: { ...task, id: "other-task" } }));
  expect(screen.getByRole("searchbox")).toHaveValue("");
  expect(screen.getByRole("combobox", { name: "日志 Listing" })).toHaveValue("");
});

test("快捷入口精确选片段，重复进入清除旧组合条件，无日志时仍显示目标", async () => {
  const user = userEvent.setup();
  const focusListing = { key: "key-a", label: "DEMO" };
  const { rerender } = render(view("events", { focusListing }));
  expect(screen.getByRole("combobox", { name: "日志 Listing" })).toHaveValue("key-a");
  await user.type(screen.getByRole("searchbox"), "旧条件");
  await user.selectOptions(
    screen.getByRole("combobox", { name: "日志事件类型" }),
    "segment_progress",
  );
  rerender(view("events", { focusListing: { ...focusListing } }));
  expect(screen.getByRole("searchbox")).toHaveValue("");
  expect(screen.getByRole("combobox", { name: "日志事件类型" })).toHaveValue("");
  rerender(
    view("events", {
      events: [],
      focusListing: { key: "key-b", label: "DEMO", store: "OTHER:US" },
    }),
  );
  expect(screen.getByRole("combobox", { name: "日志 Listing" })).toHaveDisplayValue(
    "DEMO · OTHER:US",
  );
  expect(screen.getByText("没有匹配的日志。")).toBeVisible();
});
