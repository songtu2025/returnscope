import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test } from "vitest";
import { TaskEventList } from "../src/features/task-runtime/TaskEventList";

afterEach(cleanup);

const task = {
  segments: [
    { id: "segment-a", segment_key: "key-a", scope: { listing: "DEMO-A" } },
    {
      id: "segment-b",
      segment_key: "key-b",
      scope: { listing: "DEMO-B" },
      deleted_at: "2026-10-02",
    },
  ],
};

function event(data = {}) {
  return {
    id: 1,
    stage: "任务结束",
    message: "Listing 取消请求已提交",
    event_type: "segment_cancel",
    created_at: "2026-10-01T00:00:00Z",
    actor_name: "合成用户",
    data,
  };
}

test.each([
  [{ segment_id: "segment-a" }, "DEMO-A"],
  [{ segment_key: "key-a" }, "DEMO-A"],
  [{ segment_key: "key-b" }, "DEMO-B"],
  [{ segment_key: "unresolved-key" }, "unresolved-key"],
  [{ segment_id: "unresolved-id" }, "unresolved-id"],
])("日志复用片段标识解析并保留无法解析的原始标识 %j", (data, listing) => {
  render(<TaskEventList task={task} events={[event(data)]} />);
  expect(screen.getByText(`${listing} · 任务结束`)).toBeVisible();
  expect(screen.getByText("操作人：合成用户")).toBeVisible();
});

test("操作事件展示平铺状态和原因，不改写原始事件", () => {
  const value = event({
    segment_key: "key-a",
    before_status: "running",
    after_status: "cancel_requested",
    note: "合成取消原因",
  });
  render(<TaskEventList task={task} events={[value]} />);
  expect(screen.getByText(/原状态：分析中/)).toHaveTextContent("新状态：正在取消");
  expect(screen.getByText("原因：合成取消原因")).toBeVisible();
  expect(value.data.after_status).toBe("cancel_requested");
});

test("历史嵌套状态、名称变更和独立原因继续展示且不重复原因", () => {
  render(
    <TaskEventList
      task={task}
      events={[
        event({
          before: { status: "paused", title: "合成旧名称" },
          after: { status: "queued", title: "合成新名称" },
          note: "合成更名原因",
        }),
        { ...event({ note: "合成独立原因" }), id: 2 },
      ]}
    />,
  );
  expect(screen.getByText(/原状态：已暂停/)).toHaveTextContent("新状态：排队中");
  expect(screen.getByText(/原值：合成旧名称/)).toHaveTextContent("新值：合成新名称");
  expect(screen.getAllByText("原因：合成更名原因")).toHaveLength(1);
  expect(screen.getByText("原因：合成独立原因")).toBeVisible();
});

test("任务级日志不虚构 Listing，未知状态与缺失另一侧保持可读", () => {
  render(
    <TaskEventList task={task} events={[event({ before_status: "legacy_unknown" })]} />,
  );
  expect(screen.getByText("任务结束", { exact: true })).toBeVisible();
  expect(screen.getByText(/原状态：legacy_unknown/)).toHaveTextContent("新状态：—");
});

test("完整日志先筛选全部事件再分批展示，重置返回最近100条", async () => {
  const user = userEvent.setup();
  const events = [
    { ...event(), message: "合成早期线索", event_type: "created" },
    ...Array.from({ length: 204 }, (_, index) => ({
      ...event({ segment_id: "segment-b" }),
      id: index + 2,
      message: `合成进度 ${index}`,
      event_type: "segment_progress",
    })),
  ];
  render(<TaskEventList task={task} events={events} filterable />);
  expect(screen.getByRole("status")).toHaveTextContent("共 205 条日志");
  expect(screen.queryByText("合成早期线索")).toBeNull();
  await user.click(
    screen.getByRole("button", { name: "加载更早日志（已显示 100 / 205 条）" }),
  );
  const search = screen.getByRole("searchbox", { name: "搜索运行日志" });
  await user.type(search, "早期线索");
  expect(screen.getByRole("status")).toHaveTextContent("匹配 1 / 205 条");
  expect(screen.getByText("合成早期线索")).toBeVisible();
  expect(screen.queryByRole("button", { name: /加载更早日志/ })).toBeNull();
  await user.clear(search);
  await user.type(search, "不存在XYZ");
  expect(screen.getByText("没有匹配的日志。")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "重置日志筛选" }));
  expect(search).toHaveValue("");
  expect(
    screen.getByRole("button", { name: "加载更早日志（已显示 100 / 205 条）" }),
  ).toBeVisible();
});

test("Listing 筛选合并同一片段两种标识、组合类型并随实时事件更新", async () => {
  const user = userEvent.setup();
  const events = [
    event({ segment_id: "segment-a" }),
    { ...event({ segment_key: "key-a" }), id: 2, event_type: "segment_pause" },
    { ...event({ segment_key: "key-b" }), id: 3 },
    { ...event({ segment_key: "unknown-key" }), id: 4 },
  ];
  const { rerender } = render(<TaskEventList task={task} events={events} filterable />);
  expect(screen.getAllByRole("option", { name: "DEMO-A" })).toHaveLength(1);
  expect(screen.getByRole("option", { name: "unknown-key" })).toBeVisible();
  await user.selectOptions(
    screen.getByRole("combobox", { name: "日志 Listing" }),
    "key-a",
  );
  expect(screen.getByRole("status")).toHaveTextContent("匹配 2 / 4 条");
  await user.selectOptions(
    screen.getByRole("combobox", { name: "日志事件类型" }),
    "segment_cancel",
  );
  expect(screen.getByRole("status")).toHaveTextContent("匹配 1 / 4 条");
  rerender(
    <TaskEventList
      task={task}
      events={[
        ...events,
        { ...event({ segment_key: "key-a" }), id: 5, message: "合成实时取消" },
      ]}
      filterable
    />,
  );
  expect(screen.getByRole("status")).toHaveTextContent("匹配 2 / 5 条");
  expect(screen.getByText("合成实时取消")).toBeVisible();
  expect(screen.queryByText("DEMO-B · 任务结束")).toBeNull();
  expect(screen.getByRole("combobox", { name: "日志 Listing" })).toHaveValue("key-a");
});

test.each(["demo-a", "合成用户", "合成原因", "合成旧名称", "正在取消"])(
  "关键词搜索已有展示信息 %s",
  async (query) => {
    const user = userEvent.setup();
    render(
      <TaskEventList
        task={task}
        events={[
          event({
            segment_key: "key-a",
            note: "合成原因",
            before: { title: "合成旧名称" },
            after_status: "cancel_requested",
          }),
        ]}
        filterable
      />,
    );
    await user.type(screen.getByRole("searchbox", { name: "搜索运行日志" }), query);
    expect(screen.getByRole("status")).toHaveTextContent("匹配 1 / 1 条");
  },
);

test("空日志保留真实空态，摘要日志不增加完整筛选栏", () => {
  const { rerender } = render(<TaskEventList task={task} events={[]} filterable />);
  expect(screen.getByText("暂无运行动态。")).toBeVisible();
  expect(screen.getByRole("status")).toHaveTextContent("共 0 条日志");
  expect(screen.getByRole("button", { name: "重置日志筛选" })).toBeDisabled();
  rerender(<TaskEventList task={task} events={[event()]} />);
  expect(screen.queryByRole("searchbox")).toBeNull();
});
