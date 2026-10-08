import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { SegmentBoard } from "../src/features/task-runtime/SegmentBoard";
import { renderWithServerState as render } from "./renderWithServerState";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function segment(index, fields = {}) {
  return {
    id: `synthetic-${index}`,
    segment_key: `synthetic-key-${index}`,
    agent_key: "footwear",
    agent_family: "合成智能体",
    standard_name: "合成标准",
    scope: { store: "SYNTHETIC", listing: `SYNTHETIC-${index}` },
    status: "queued",
    record_count: 10,
    unique_comments: 5,
    progress_current: 0,
    progress_total: 5,
    variants: [],
    ...fields,
  };
}

function propsFor(segments, fields = {}) {
  return {
    task: {
      id: "synthetic-task",
      title: "合成任务",
      status: "running",
      revision: 1,
      owner_name: "合成用户",
      created_at: "2026-10-01T00:00:00Z",
      segments,
      ...fields,
    },
    onRetry: vi.fn(),
    onRetryPublish: vi.fn(),
    onCancel: vi.fn(),
    onAction: vi.fn(),
    onParallelism: vi.fn(),
    onReorder: vi.fn(),
    onViewClassification: vi.fn(),
    onResumeUnfinished: vi.fn(),
  };
}

test("每页20条，搜索跨全部Listing并重置页码，数据减少后修正页码", async () => {
  const user = userEvent.setup();
  const segments = Array.from({ length: 25 }, (_, index) => segment(index));
  const props = propsFor(segments);
  const view = render(<SegmentBoard {...props} />);
  expect(view.container.querySelectorAll("article.listing-row")).toHaveLength(20);
  await user.click(screen.getByRole("button", { name: "下一页" }));
  expect(view.container.querySelectorAll("article.listing-row")).toHaveLength(5);
  expect(screen.getByText("SYNTHETIC-24")).toBeVisible();
  expect(screen.getByLabelText("第 2 页")).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "上一页" }));
  expect(screen.getByLabelText("第 1 页")).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "下一页" }));
  await user.type(screen.getByRole("textbox", { name: "搜索 Listing" }), "SYNTHETIC-5");
  await waitFor(() =>
    expect(view.container.querySelectorAll("article.listing-row")).toHaveLength(1),
  );
  expect(screen.getByText("SYNTHETIC-5")).toBeVisible();
  expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled();
  await user.clear(screen.getByRole("textbox", { name: "搜索 Listing" }));
  await waitFor(() =>
    expect(view.container.querySelectorAll("article.listing-row")).toHaveLength(20),
  );
  await user.click(screen.getByRole("button", { name: "下一页" }));
  view.rerender(
    <SegmentBoard
      {...props}
      task={{ ...props.task, segments: segments.slice(0, 3) }}
    />,
  );
  await waitFor(() => expect(screen.getByText("SYNTHETIC-0")).toBeVisible());
  expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled();
});

test("已生成结果包含已发布和旧结果，需处理筛选与执行状态独立", async () => {
  const user = userEvent.setup();
  const view = render(
    <SegmentBoard
      {...propsFor([
        segment(0, {
          status: "completed",
          result_version_id: "synthetic-result",
          result_publish_status: "published",
          result_quality_status: "ready",
        }),
        segment(1, { status: "completed", result_file_path: "synthetic.xlsx" }),
        segment(2, { status: "failed", error: "合成异常" }),
        segment(3, { status: "paused" }),
      ])}
    />,
  );
  await user.selectOptions(screen.getByLabelText("按 Listing 状态筛选"), "delivered");
  expect(view.container.querySelectorAll("article.listing-row")).toHaveLength(2);
  expect(screen.getByText("SYNTHETIC-0")).toBeVisible();
  expect(screen.getByText("SYNTHETIC-1")).toBeVisible();
  await user.selectOptions(screen.getByLabelText("按 Listing 状态筛选"), "attention");
  expect(view.container.querySelectorAll("article.listing-row")).toHaveLength(1);
  expect(screen.getByText("SYNTHETIC-2")).toBeVisible();
  expect(screen.queryByText("SYNTHETIC-3")).not.toBeInTheDocument();
});

test("目标焦点在全部筛选下跨页定位，滚动到带aria-current的目标行", async () => {
  const scroll = vi.spyOn(HTMLElement.prototype, "scrollIntoView");
  const segments = Array.from({ length: 25 }, (_, index) => segment(index));
  render(
    <SegmentBoard
      {...propsFor(segments)}
      initialFilter="all"
      focusSegmentId="synthetic-24"
    />,
  );
  const row = (await screen.findByText("SYNTHETIC-24")).closest("article");
  expect(row).toHaveAttribute("aria-current", "true");
  expect(screen.getByLabelText("按 Listing 状态筛选")).toHaveValue("all");
  expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
  await waitFor(() => expect(scroll).toHaveBeenCalledWith({ block: "center" }));
});

test("未知品类只进入排除数量说明，不生成Listing行", () => {
  const view = render(
    <SegmentBoard
      {...propsFor([
        segment(0),
        segment(1, { agent_key: "unknown", record_count: 1000, unique_comments: 100 }),
        segment(2, { agent_key: "unknown", record_count: 2000, unique_comments: 200 }),
      ])}
    />,
  );
  expect(view.container.querySelectorAll("article.listing-row")).toHaveLength(1);
  expect(screen.getByText("未配置品类的数据未纳入语义分析")).toBeVisible();
  expect(screen.getByText(/3,000 条记录 \/ 300/)).toBeVisible();
  expect(screen.queryByText("SYNTHETIC-1")).not.toBeInTheDocument();
});

test("调整并行数期间禁用增减按钮，服务端返回后恢复操作", async () => {
  const props = propsFor([segment(0)], { max_parallel_segments: 2 });
  let finish;
  props.onParallelism.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  render(<SegmentBoard {...props} />);
  await userEvent.click(screen.getByText("执行设置"));
  await userEvent.click(screen.getByRole("button", { name: "增加 Listing 并行数" }));
  expect(props.onParallelism).toHaveBeenCalledExactlyOnceWith(3);
  expect(screen.getByRole("button", { name: "增加 Listing 并行数" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "减少 Listing 并行数" })).toBeDisabled();
  finish(false);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "减少 Listing 并行数" })).toBeEnabled(),
  );
});

test("展开后拖拽排序只提交可排序片段，提交期间阻止重复操作", async () => {
  const props = propsFor([segment(0), segment(1), segment(2, { status: "running" })]);
  let finish;
  props.onReorder.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  render(<SegmentBoard {...props} />);
  const first = screen.getByText("SYNTHETIC-0").closest("article");
  const second = screen.getByText("SYNTHETIC-1").closest("article");
  await userEvent.click(within(first).getByRole("button", { name: "查看详情" }));
  expect(first).toHaveAttribute("draggable", "true");
  const transfer = {
    setData: vi.fn(),
    getData: vi.fn(() => "synthetic-key-0"),
    effectAllowed: "",
  };
  fireEvent.dragStart(first, { dataTransfer: transfer });
  expect(transfer.setData).toHaveBeenCalledWith("text/plain", "synthetic-key-0");
  fireEvent.drop(second, { dataTransfer: transfer });
  expect(props.onReorder).toHaveBeenCalledExactlyOnceWith([
    "synthetic-key-1",
    "synthetic-key-0",
  ]);
  expect(
    within(first).getByRole("button", { name: "下移 SYNTHETIC-0" }),
  ).toBeDisabled();
  fireEvent.drop(second, { dataTransfer: transfer });
  expect(props.onReorder).toHaveBeenCalledOnce();
  finish(false);
  await waitFor(() =>
    expect(
      within(first).getByRole("button", { name: "下移 SYNTHETIC-0" }),
    ).toBeEnabled(),
  );
});

test("没有执行片段时不渲染队列；搜索无结果保留条件及分页说明", async () => {
  const props = propsFor([]);
  const view = render(<SegmentBoard {...props} />);
  expect(
    screen.queryByRole("region", { name: "Listing 执行队列" }),
  ).not.toBeInTheDocument();
  view.rerender(
    <SegmentBoard {...props} task={{ ...props.task, segments: [segment(0)] }} />,
  );
  await userEvent.type(screen.getByLabelText("搜索 Listing"), "不存在的合成Listing");
  expect(await screen.findByText("没有匹配的 Listing。")).toBeVisible();
  expect(screen.getByLabelText("搜索 Listing")).toHaveValue("不存在的合成Listing");
  expect(screen.getByText("共 0 条")).toBeVisible();
});
