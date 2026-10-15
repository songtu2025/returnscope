import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

const { taskMonitorProbe } = vi.hoisted(() => ({
  taskMonitorProbe: vi.fn(),
}));

vi.mock("../src/features/task-runtime/TaskMonitor", () => ({
  TaskMonitor: (props) => {
    taskMonitorProbe(props);
    return <div>任务运行内容</div>;
  },
}));

import { TaskRuntimePage } from "../src/features/task-runtime/TaskRuntimePage";
import { SegmentBoardRow } from "../src/features/task-runtime/SegmentBoardRow";
import { renderWithServerState as render } from "./renderWithServerState";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  window.sessionStorage.clear();
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

test("任务列表筛选写入 URL 并保留任务焦点", () => {
  window.location.hash =
    "#analysis-tasks?task_id=task-1&status=active&q=%E6%89%8B%E5%A5%97&owner=%E7%AE%A1%E7%90%86%E5%91%98&sort=progress_desc&attention=1";
  render(
    <TaskRuntimePage
      route={{
        query: {
          task_id: "task-1",
          status: "active",
          q: "手套",
          owner: "管理员",
          sort: "progress_desc",
          attention: "1",
        },
      }}
      notify={vi.fn()}
      onNavigate={vi.fn()}
      onChanged={vi.fn()}
    />,
  );

  const props = taskMonitorProbe.mock.calls.at(-1)[0];
  expect(props.listState).toEqual({
    filter: "active",
    query: "手套",
    owner: "管理员",
    sort: "progress_desc",
    attentionOnly: true,
  });

  props.onListStateChange({ query: "冬季手套", filter: "finished" });
  expect(window.location.hash).toContain("task_id=task-1");
  expect(window.location.hash).toContain("status=finished");
  expect(window.location.hash).toContain("q=%E5%86%AC%E5%AD%A3%E6%89%8B%E5%A5%97");

  props.onTaskFocus(null);
  expect(window.location.hash).not.toContain("task_id");
  expect(window.location.hash).toContain("status=active");
});

test("后端标记系统异常可重试时展示专用入口并复用 Listing 重试动作", async () => {
  const onRetry = vi.fn();
  const segment = {
    id: "segment-1",
    segment_key: "STORE\u001fLISTING",
    agent_key: "agent-1",
    agent_family: "服装",
    scope: { store: "STORE", listing: "LISTING" },
    status: "completed_with_errors",
    display_status: "completed_with_errors",
    record_count: 3,
    unique_comments: 2,
    progress_current: 3,
    progress_total: 3,
    result_version_id: "result-1",
    result_publish_status: "published",
    system_retry_available: true,
    system_failure_count: 2,
  };

  render(
    <SegmentBoardRow
      task={{
        id: "task-1",
        title: "退货分析",
        status: "completed",
        revision: 1,
        owner_name: "测试用户",
        created_at: "2026-09-17T08:00:00Z",
        store: "STORE",
        segments: [segment],
      }}
      segment={segment}
      position={{
        segmentIndex: 0,
        page: 1,
        pageSize: 20,
        focusSegmentId: null,
        focusedSegmentRef: { current: null },
      }}
      queue={{
        canManageQueue: false,
        orderableKeys: [],
        reordering: false,
        applyOrder: vi.fn(),
      }}
      rowState={{
        expandedSegmentKey: null,
        setExpandedSegmentKey: vi.fn(),
        retryingPublishId: null,
        setRetryingPublishId: vi.fn(),
      }}
      actions={{
        onResumeUnfinished: vi.fn(),
        onAction: vi.fn(),
        onRetry,
        onViewClassification: vi.fn(),
        onRetryPublish: vi.fn(),
      }}
    />,
  );

  const retryButton = screen.getByRole("button", { name: "重试失败项" });
  expect(retryButton).toHaveAttribute("title", "重新分析 2 个失败项");
  expect(screen.queryByRole("button", { name: "重试" })).toBeNull();
  await userEvent.click(retryButton);
  expect(onRetry).toHaveBeenCalledWith(segment);
});
