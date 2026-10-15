import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { renderWithServerState as render } from "./renderWithServerState";
import { TaskDetail } from "../src/features/task-runtime/TaskDetail";

afterEach(cleanup);

function propsFor(status) {
  return {
    task: {
      id: "synthetic-task",
      title: "合成任务",
      status,
      revision: 7,
      segments: [],
    },
    events: [],
    actionError: "",
    ...Object.fromEntries(
      [
        "onClearActionError",
        "onTaskRenamed",
        "onArchive",
        "onPause",
        "onResume",
        "onRetry",
        "onRetrySegment",
        "onRetryResultPublish",
        "onSegmentAction",
        "onParallelism",
        "onReorderSegments",
        "onPreflightReplan",
        "onReplan",
        "onViewClassification",
      ].map((name) => [name, vi.fn().mockResolvedValue(true)]),
    ),
  };
}

test.each([
  ["running", "onPause", "暂停未完成", "正在暂停…"],
  ["failed", "onRetry", "重新运行", "正在创建任务…"],
  ["completed", "onRetry", "再次运行", "正在创建任务…"],
  ["completed", "onArchive", "归档任务", "正在归档任务…"],
])(
  "%s任务的%s阻止同一轮重复提交，待结束后恢复",
  async (status, key, label, pending) => {
    const props = propsFor(status);
    let finish;
    props[key].mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    render(<TaskDetail {...props} />);
    if (status === "completed")
      await userEvent.click(screen.getByLabelText("更多任务操作"));
    const action = screen.getByRole("button", { name: label });
    act(() => {
      action.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      action.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(props[key]).toHaveBeenCalledOnce();
    expect(
      screen.getByRole("button", { name: "修改任务名称：合成任务" }),
    ).toBeDisabled();
    expect(screen.getByText(pending, { selector: "span[role=status]" })).toBeVisible();
    await userEvent.click(screen.getByLabelText("更多任务操作"));
    if (status === "completed") {
      expect(screen.getByRole("button", { name: "再次运行" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "归档任务" })).toBeDisabled();
    }
    await act(async () => finish(false));
    await waitFor(() =>
      expect(screen.queryByText(pending, { selector: "span[role=status]" })).toBeNull(),
    );
    expect(props[key]).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: label })).toBeEnabled();
  },
);

test("意外失败保留就地错误并解除忙态，允许再次执行", async () => {
  const props = propsFor("running");
  props.onPause.mockRejectedValueOnce(new Error("合成提交失败"));
  render(<TaskDetail {...props} />);
  await userEvent.click(screen.getByRole("button", { name: "暂停未完成" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("合成提交失败");
  expect(screen.getByRole("button", { name: "暂停未完成" })).toBeEnabled();
  await userEvent.click(screen.getByRole("button", { name: "暂停未完成" }));
  expect(props.onPause).toHaveBeenCalledTimes(2);
  expect(screen.queryByRole("alert")).toBeNull();
});

test.each([
  ["onSegmentAction", "暂停"],
  ["onRetryResultPublish", "重试生成结果"],
  ["onParallelism", "增加 Listing 并行数"],
  ["onReorderSegments", "下移 LIST-0"],
  ["onSegmentAction", "确认移除 Listing"],
  ["onRetrySegment", "确认重试片段"],
])("Listing先发起%s时统一锁定任务写操作，完成后无互锁", async (key, label) => {
  const props = propsFor("paused");
  props.task.max_parallel_segments = 2;
  props.task.segments = [0, 1].map((index) => ({
    id: `item-${index}`,
    segment_key: `key-${index}`,
    agent_key: "footwear",
    status:
      index === 0 && key === "onRetryResultPublish"
        ? "completed"
        : index === 0 && key === "onRetrySegment"
          ? "failed"
          : "queued",
    result_publish_status: key === "onRetryResultPublish" ? "failed" : "none",
    scope: { listing: `LIST-${index}` },
    record_count: 1,
    progress_current: 0,
    progress_total: 1,
  }));
  let finish;
  props[key].mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  render(<TaskDetail {...props} />);
  if (key === "onParallelism") await userEvent.click(screen.getByText("执行设置"));
  if (key === "onReorderSegments")
    await userEvent.click(screen.getByRole("button", { name: "查看 LIST-0 详情" }));
  if (label === "确认移除 Listing") {
    const menu = screen.getByLabelText("更多 Listing 操作：LIST-0");
    await userEvent.click(menu);
    await userEvent.click(
      within(menu.closest("details")).getByRole("button", { name: "移除 Listing" }),
    );
  }
  if (key === "onRetrySegment")
    await userEvent.click(screen.getByRole("button", { name: "重试", exact: true }));
  const submit = screen.getAllByRole("button", { name: label, exact: true })[0];
  act(() => {
    submit.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    submit.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  expect(props[key]).toHaveBeenCalledOnce();
  expect(
    screen.getByRole("button", { name: "继续未完成", exact: true }),
  ).toBeDisabled();
  expect(screen.getByRole("button", { name: "修改任务名称：合成任务" })).toBeDisabled();
  await act(async () => finish(false));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "继续未完成", exact: true }),
    ).toBeEnabled(),
  );
  expect(props[key]).toHaveBeenCalledOnce();
});

test("任务继续提交时锁定同任务Listing写操作，保留详情和结果读取", async () => {
  const props = propsFor("paused");
  props.task.max_parallel_segments = 2;
  props.task.segments = ["queued", "paused", "failed", "completed"].map(
    (status, index) => ({
      id: `synthetic-${index}`,
      segment_key: `key-${index}`,
      agent_key: "footwear",
      status,
      scope: { listing: `SYNTHETIC-${index}` },
      record_count: 1,
      unique_comments: 1,
      progress_current: 0,
      progress_total: 1,
      result_version_id: index === 3 ? "result" : null,
      result_publish_state: index === 3 ? "published" : "none",
    }),
  );
  let finish;
  props.onResume.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  render(<TaskDetail {...props} />);
  await userEvent.click(
    screen.getByRole("button", { name: "继续未完成", exact: true }),
  );
  await userEvent.click(screen.getByRole("button", { name: "继续未完成片段" }));
  for (const name of ["暂停", "继续", "重试"])
    expect(screen.getByRole("button", { name, exact: true })).toBeDisabled();
  await userEvent.click(screen.getByText("执行设置"));
  for (const name of ["减少 Listing 并行数", "增加 Listing 并行数"])
    expect(screen.getByRole("button", { name })).toBeDisabled();
  const more = screen.getByLabelText("更多 Listing 操作：SYNTHETIC-0");
  expect(more).toHaveAttribute("aria-disabled", "true");
  const detail = screen.getByRole("button", { name: "查看 SYNTHETIC-0 详情" });
  expect(detail).toBeEnabled();
  await userEvent.click(detail);
  expect(screen.queryByRole("button", { name: "上移" })).toBeNull();
  expect(screen.getByRole("button", { name: "查看结果", exact: true })).toBeEnabled();
  await act(async () => finish(false));
  expect(screen.getByRole("button", { name: "暂停", exact: true })).toBeEnabled();
  expect(props.onSegmentAction).not.toHaveBeenCalled();
});
