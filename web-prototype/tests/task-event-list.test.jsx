import { cleanup, render, screen } from "@testing-library/react";
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
