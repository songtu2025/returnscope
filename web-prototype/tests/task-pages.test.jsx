import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

const { apiProbe, newTaskPageProbe, taskMonitorProbe } = vi.hoisted(() => ({
  apiProbe: { task: vi.fn() },
  newTaskPageProbe: vi.fn(),
  taskMonitorProbe: vi.fn(),
}));

vi.mock("../src/api", () => ({ api: apiProbe }));

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
import {
  readTaskDraft,
  writeTaskDraft,
} from "../src/features/task-create/taskDraftStorage";
import { TaskRuntimePage } from "../src/features/task-runtime/TaskRuntimePage";
import { SegmentBoardRow } from "../src/features/task-runtime/SegmentBoardRow";

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
    dataEntryMode: "existing",
    selectedDataLabel: "当前完整数据",
    form: { dataset_version_id: "returns-v7" },
  });
});

test("重新进入任务创建页时保留已选数据和输入", () => {
  writeTaskDraft("user-1", {
    step: 1,
    resumePreflight: false,
    form: {
      title: "待创建任务",
      dataset_version_id: "returns-v6",
    },
    dataEntryMode: "existing",
    selectedDataLabel: "当前完整数据",
  });

  render(
    <TaskCreatePage
      route={{ query: {} }}
      notify={vi.fn()}
      onNavigate={vi.fn()}
      onChanged={vi.fn()}
      userId="user-1"
    />,
  );

  expect(newTaskPageProbe.mock.calls.at(-1)[0].draft).toMatchObject({
    dataEntryMode: "existing",
    selectedDataLabel: "当前完整数据",
    form: { title: "待创建任务", dataset_version_id: "returns-v6" },
  });
  expect(readTaskDraft("user-1")).toMatchObject({
    dataEntryMode: "existing",
    selectedDataLabel: "当前完整数据",
    form: { dataset_version_id: "returns-v6" },
  });
});

test("商品修复返回任务创建页时保留待恢复的退货版本", () => {
  writeTaskDraft("user-1", {
    step: 3,
    resumePreflight: true,
    form: { dataset_version_id: "returns-v6" },
  });

  render(
    <TaskCreatePage
      route={{ query: {} }}
      notify={vi.fn()}
      onNavigate={vi.fn()}
      onChanged={vi.fn()}
      userId="user-1"
    />,
  );

  expect(newTaskPageProbe.mock.calls.at(-1)[0].draft).toMatchObject({
    step: 3,
    resumePreflight: true,
    form: { dataset_version_id: "returns-v6" },
  });
});

test("创建类似任务时只继承名称和模型策略", async () => {
  apiProbe.task.mockResolvedValue({
    id: "task-template",
    title: "历史分析任务",
    dataset_name: "退货数据",
    dataset_version: 7,
    dataset_version_id: "returns-v7",
    product_version_id: "products-v3",
    config_version_id: "config-v2",
    snapshot: {
      config: {
        connection_id: "connection-1",
        cheap_model: "gpt-5.6-luna",
        cheap_effort: "low",
        primary_model: "gpt-5.6-terra",
        primary_effort: "medium",
        secondary_model: "gpt-5.6-sol",
        secondary_effort: "high",
        cheap_audit_percent: 10,
      },
    },
  });

  render(
    <TaskCreatePage
      route={{ query: { template_task: "task-template" } }}
      notify={vi.fn()}
      onNavigate={vi.fn()}
      onChanged={vi.fn()}
      userId="user-1"
    />,
  );

  expect(screen.getByText("正在读取原任务配置…")).toBeVisible();
  await waitFor(() => expect(newTaskPageProbe).toHaveBeenCalled());
  expect(newTaskPageProbe.mock.calls.at(-1)[0].draft).toMatchObject({
    step: 1,
    dataEntryMode: "existing",
    selectedDataLabel: "",
    form: {
      title: "历史分析任务（副本）",
      dataset_version_id: "",
      product_version_id: "",
      config_version_id: "config-v2",
      store: "",
      listing: "",
      model_policy: {
        connection_id: "connection-1",
        cheap_model: "gpt-5.6-luna",
        primary_model: "gpt-5.6-terra",
        secondary_model: "gpt-5.6-sol",
      },
    },
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
        onCancel: vi.fn(),
      }}
    />,
  );

  const retryButton = screen.getByRole("button", { name: "重试系统异常" });
  expect(retryButton).toHaveAttribute("title", "重新处理 2 个系统异常");
  expect(screen.queryByRole("button", { name: "重试" })).toBeNull();
  await userEvent.click(retryButton);
  expect(onRetry).toHaveBeenCalledWith(segment);
});
