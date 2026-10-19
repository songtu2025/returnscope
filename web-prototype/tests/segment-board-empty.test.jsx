import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { SegmentBoard } from "../src/features/task-runtime/SegmentBoard";
import { parseHash } from "../src/app/hashRouter";
import { renderWithServerState as render } from "./renderWithServerState";

afterEach(() => {
  cleanup();
  window.history.replaceState({}, "", "/");
});

const item = {
  id: "empty-proof",
  segment_key: "empty-key",
  agent_key: "footwear",
  scope: { listing: "合成 Listing", store: "合成店铺" },
  status: "completed",
  record_count: 8,
  unique_comments: 4,
  progress_current: 4,
  progress_total: 4,
  variants: [],
};

function show(segments) {
  const onAction = vi.fn();
  render(
    <SegmentBoard
      task={{
        id: "empty-task",
        title: "合成任务 & 同名 / 范围",
        status: "completed",
        segments,
      }}
      onAction={onAction}
      onRetry={vi.fn()}
      onRetryPublish={vi.fn()}
      onParallelism={vi.fn()}
      onReorder={vi.fn()}
      onViewClassification={vi.fn()}
    />,
  );
  return onAction;
}

test("全部移除后说明原因，键盘打开按名称搜索的回收站且不写记录", async () => {
  const onAction = show([{ ...item, deleted_at: "2026-10-19" }]);
  expect(screen.getByText("暂无可执行 Listing")).toBeVisible();
  expect(screen.getByText(/本任务有 1 个 Listing 已移至回收站/)).toHaveTextContent(
    "可能包含同名任务，请核对所属任务",
  );
  const button = screen.getByRole("button", { name: "查看回收站" });
  button.focus();
  await userEvent.keyboard("{Enter}");
  expect(parseHash()).toMatchObject({
    page: "analysis-tasks",
    query: { view: "recycle", q: "合成任务 & 同名 / 范围" },
  });
  expect(onAction).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "恢复 Listing" })).toBeNull();
});

test.each([undefined, []])("无执行项时解释并引导现有配置页签 %s", (segments) => {
  show(segments);
  expect(screen.getByText(/本任务尚无 Listing 执行项/)).toHaveTextContent("任务配置");
  expect(screen.queryByRole("button", { name: "查看回收站" })).toBeNull();
});

test("只有未配置品类的数据时复用现有排除明细", () => {
  show([{ ...item, agent_key: "unknown" }]);
  expect(screen.getByText(/当前数据均未纳入 Listing 执行/)).toBeVisible();
  expect(screen.getByText(/8 条记录/)).toHaveTextContent("4组评论");
  expect(screen.queryByRole("button", { name: "查看回收站" })).toBeNull();
});

test("已移除的未配置项不再计入当前排除明细", () => {
  show([{ ...item, agent_key: "unknown", deleted_at: "2026-10-19" }]);
  expect(screen.getByText(/本任务有 1 个 Listing 已移至回收站/)).toBeVisible();
  expect(screen.queryByText("未配置品类的数据未纳入语义分析")).toBeNull();
});

test("移除项与当前排除项共存时分别解释", () => {
  show([
    { ...item, deleted_at: "2026-10-19" },
    { ...item, id: "excluded", segment_key: "excluded", agent_key: "unknown" },
  ]);
  expect(screen.getByText(/本任务有 1 个 Listing 已移至回收站/)).toBeVisible();
  expect(screen.getByText("未配置品类的数据未纳入语义分析")).toBeVisible();
  expect(screen.queryByText(/当前数据均未纳入/)).toBeNull();
});

test("正常执行行与搜索无匹配不显示任务空态", async () => {
  show([item, { ...item, id: "removed", deleted_at: "2026-10-19" }]);
  expect(screen.getByText("合成 Listing")).toBeVisible();
  expect(screen.queryByText("暂无可执行 Listing")).toBeNull();
  await userEvent.type(screen.getByRole("textbox", { name: "搜索 Listing" }), "无匹配");
  expect(await screen.findByText("没有匹配的 Listing。")).toBeVisible();
  expect(screen.queryByRole("button", { name: "查看回收站" })).toBeNull();
});
