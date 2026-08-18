import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

const { newTaskPageProbe, taskMonitorProbe } = vi.hoisted(() => ({
  newTaskPageProbe: vi.fn(),
  taskMonitorProbe: vi.fn(),
}));

vi.mock("../src/features/task-create/NewTaskPage", () => ({
  NewTaskPage: (props) => {
    newTaskPageProbe(props);
    return <div>任务创建内容</div>;
  },
}));

vi.mock("../src/features/task-runtime/TaskMonitor", () => ({
  TaskMonitor: (props) => {
    taskMonitorProbe(props);
    return <div>任务运行内容</div>;
  },
}));

import { TaskCreatePage } from "../src/features/task-create/TaskCreatePage";
import { TaskRuntimePage } from "../src/features/task-runtime/TaskRuntimePage";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  window.sessionStorage.clear();
});

test("任务创建页将数据版本写入用户草稿并保留业务归属", () => {
  render(
    <TaskCreatePage
      route={{ query: { dataset_version: "returns-v7" } }}
      notify={vi.fn()}
      onNavigate={vi.fn()}
      onChanged={vi.fn()}
      userId="user-1"
    />,
  );

  expect(screen.getByRole("navigation", { name: "面包屑" })).toHaveTextContent(
    "分析任务/创建任务",
  );
  expect(newTaskPageProbe.mock.calls.at(-1)[0].draft).toMatchObject({
    form: { dataset_version_id: "returns-v7" },
  });
});

test("任务运行页把任务和 Listing 焦点传给监控器", () => {
  render(
    <TaskRuntimePage
      route={{ query: { task_id: "task-1", segment_id: "segment-2" } }}
      notify={vi.fn()}
      onNavigate={vi.fn()}
      onChanged={vi.fn()}
    />,
  );

  expect(screen.getByText("任务运行内容")).toBeVisible();
  expect(taskMonitorProbe.mock.calls.at(-1)[0]).toMatchObject({
    focusId: "task-1",
    focusSegmentId: "segment-2",
  });
});
