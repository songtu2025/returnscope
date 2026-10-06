import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { SegmentBoardRow } from "../src/features/task-runtime/SegmentBoardRow";
import { renderWithServerState as render } from "./renderWithServerState";

afterEach(cleanup);

function rowProps(fields = {}, status = "paused") {
  const segment = {
    id: "synthetic-segment",
    segment_key: "synthetic-key",
    agent_key: "footwear",
    agent_family: "合成智能体",
    scope: { listing: "SYNTHETIC", store: "合成站点" },
    status: "paused",
    record_count: 1000,
    unique_comments: 100,
    progress_current: 50,
    progress_total: 100,
    model_calls: 2,
    model_failures: 3,
    cache_hits: 1,
    taxonomy_version: "synthetic-v1",
    ...fields,
  };
  return {
    task: {
      id: "synthetic-task",
      title: "合成任务",
      status,
      revision: 1,
      owner_name: "合成用户",
      created_at: "2026-10-01T00:00:00Z",
      segments: [segment],
    },
    segment,
    position: {
      segmentIndex: 1,
      page: 2,
      pageSize: 20,
      focusSegmentId: null,
      focusedSegmentRef: { current: null },
    },
    queue: {
      canManageQueue: true,
      orderableKeys: ["synthetic-key", "synthetic-other"],
      reordering: false,
      applyOrder: vi.fn(),
    },
    rowState: {
      expandedSegmentKey: "synthetic-key",
      setExpandedSegmentKey: vi.fn(),
      retryingPublishId: null,
      setRetryingPublishId: vi.fn(),
    },
    actions: {
      onResumeUnfinished: vi.fn(),
      onAction: vi.fn(),
      onRetry: vi.fn(),
      onViewClassification: vi.fn(),
      onRetryPublish: vi.fn(),
      onCancel: vi.fn(),
    },
  };
}

test("展开详情显示请求统计、版本及操作者，位置序号按原分页计算", () => {
  render(
    <SegmentBoardRow
      {...rowProps({ standard_version: 2, logic_version: "synthetic-logic" })}
    />,
  );
  expect(screen.getByText("22")).toBeVisible();
  expect(screen.getByText("5 次请求")).toBeVisible();
  expect(screen.getByText("成功 2 · 失败 3")).toBeVisible();
  expect(screen.getByText("缓存 1 · synthetic-v1")).toBeVisible();
  expect(screen.getByText("1,000 条记录 · 100 组评论")).toBeVisible();
  expect(screen.getByText("标准 V2 · synthetic-logic")).toBeVisible();
  expect(screen.getByText("合成用户")).toBeVisible();
});

test("已发布结果使用分类版本下载，旧结果使用原任务片段下载", () => {
  const props = rowProps(
    {
      status: "completed",
      result_version_id: "synthetic-result",
      result_publish_status: "published",
      result_quality_status: "ready",
    },
    "completed",
  );
  const view = render(<SegmentBoardRow {...props} />);
  expect(screen.getByRole("link", { name: "下载" })).toHaveAttribute(
    "href",
    "/api/classification-results/synthetic-result/download",
  );
  expect(screen.queryByRole("link", { name: "下载旧结果" })).not.toBeInTheDocument();
  view.rerender(
    <SegmentBoardRow
      {...rowProps(
        { status: "completed", result_file_path: "synthetic.xlsx" },
        "completed",
      )}
    />,
  );
  expect(screen.getByRole("link", { name: "下载旧结果" })).toHaveAttribute(
    "href",
    "/api/tasks/synthetic-task/segments/synthetic-key/download",
  );
  expect(screen.getByText("旧结果 · 质量未确认")).toBeVisible();
});

test("结果生成失败显示短错误，并等待重试返回后释放操作标记", async () => {
  const props = rowProps({
    status: "completed",
    result_publish_status: "failed",
    result_publish_error: "合成发布错误",
  });
  let finish;
  props.actions.onRetryPublish.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const view = render(<SegmentBoardRow {...props} />);
  expect(screen.getByText("结果生成失败")).toBeVisible();
  expect(screen.getAllByText("合成发布错误")).toHaveLength(2);
  await userEvent.click(screen.getByRole("button", { name: "重试生成结果" }));
  expect(props.rowState.setRetryingPublishId).toHaveBeenCalledExactlyOnceWith(
    "synthetic-segment",
  );
  expect(props.actions.onRetryPublish).toHaveBeenCalledExactlyOnceWith(
    "synthetic-segment",
  );
  view.rerender(
    <SegmentBoardRow
      {...props}
      rowState={{ ...props.rowState, retryingPublishId: "synthetic-segment" }}
    />,
  );
  expect(screen.getByRole("button", { name: "正在重试" })).toBeDisabled();
  finish(false);
  await waitFor(() =>
    expect(props.rowState.setRetryingPublishId).toHaveBeenLastCalledWith(null),
  );
});

test("排序边界及提交期间禁用按键，取消使用原片段对象", async () => {
  const props = rowProps();
  const view = render(<SegmentBoardRow {...props} />);
  expect(screen.getByRole("button", { name: "置顶 SYNTHETIC" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "上移 SYNTHETIC" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "下移 SYNTHETIC" }));
  expect(props.queue.applyOrder).toHaveBeenCalledExactlyOnceWith([
    "synthetic-other",
    "synthetic-key",
  ]);
  await userEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(props.actions.onCancel).toHaveBeenCalledExactlyOnceWith(props.segment);
  view.rerender(
    <SegmentBoardRow {...props} queue={{ ...props.queue, reordering: true }} />,
  );
  expect(screen.getByRole("button", { name: "下移 SYNTHETIC" })).toBeDisabled();
});

test("收起详情隐藏下载与低频操作，切换展开通过原状态更新函数", async () => {
  const props = rowProps({ status: "completed", result_file_path: "synthetic.xlsx" });
  const view = render(
    <SegmentBoardRow
      {...props}
      rowState={{ ...props.rowState, expandedSegmentKey: null }}
    />,
  );
  expect(screen.queryByText("5 次请求")).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "下载旧结果" })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "查看详情" }));
  const update = props.rowState.setExpandedSegmentKey.mock.calls[0][0];
  expect(update(null)).toBe("synthetic-key");
  expect(update("synthetic-key")).toBeNull();
  view.rerender(<SegmentBoardRow {...props} />);
  expect(screen.getByRole("button", { name: "收起详情" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
});

test("系统异常重试优先于通用重试，运行任务禁止系统异常重试", async () => {
  const props = rowProps(
    {
      status: "completed_with_errors",
      system_retry_available: true,
      system_failure_count: 2,
    },
    "completed",
  );
  const view = render(<SegmentBoardRow {...props} />);
  const retry = screen.getByRole("button", { name: "重试系统异常" });
  expect(retry).toHaveAttribute("title", "重新处理 2 个系统异常");
  expect(screen.queryByRole("button", { name: "重试" })).not.toBeInTheDocument();
  await userEvent.click(retry);
  expect(props.actions.onRetry).toHaveBeenCalledExactlyOnceWith(props.segment);
  view.rerender(
    <SegmentBoardRow {...props} task={{ ...props.task, status: "running" }} />,
  );
  expect(
    screen.queryByRole("button", { name: "重试系统异常" }),
  ).not.toBeInTheDocument();
});

test("已取消任务保留重新排队入口，暂停与继续传入片段键", async () => {
  const props = rowProps({ status: "paused" }, "cancelled");
  const view = render(<SegmentBoardRow {...props} />);
  await userEvent.click(screen.getByRole("button", { name: "重新排队" }));
  expect(props.actions.onResumeUnfinished).toHaveBeenCalledOnce();
  await userEvent.click(screen.getByRole("button", { name: "继续" }));
  expect(props.actions.onAction).toHaveBeenCalledWith("synthetic-key", "resume");
  view.rerender(
    <SegmentBoardRow {...props} segment={{ ...props.segment, status: "queued" }} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "暂停" }));
  expect(props.actions.onAction).toHaveBeenLastCalledWith("synthetic-key", "pause");
});

test("未开始片段受原block_all策略限制，unknown片段不提供重试", () => {
  const props = rowProps({ status: "not_started" }, "failed");
  props.task.segments.push({
    ...props.segment,
    segment_key: "synthetic-blocked",
    status: "blocked",
  });
  const view = render(<SegmentBoardRow {...props} />);
  expect(screen.queryByRole("button", { name: "重试" })).not.toBeInTheDocument();
  view.rerender(
    <SegmentBoardRow
      {...props}
      task={{
        ...props.task,
        snapshot: { execution_plan: { unresolved_policy: "run_ready" } },
      }}
    />,
  );
  expect(screen.getByRole("button", { name: "重试" })).toBeVisible();
  view.rerender(
    <SegmentBoardRow {...props} segment={{ ...props.segment, agent_key: "unknown" }} />,
  );
  expect(screen.queryByRole("button", { name: "重试" })).not.toBeInTheDocument();
});
