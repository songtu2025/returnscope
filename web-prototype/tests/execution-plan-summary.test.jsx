import { cleanup, fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ExecutionPlanSummary } from "../src/features/task-planning/ExecutionPlanSummary";
import { renderWithServerState as render } from "./renderWithServerState";

afterEach(() => cleanup());

function segment(key, status = "ready") {
  return {
    segment_key: key,
    agent_family: key,
    taxonomy_version: "合成分类版本",
    status,
    record_count: 3,
    unique_comments: 2,
    variants: [{ category_a: "合成品类A", category_b: "合成品类B" }],
  };
}

function plan(changes = {}) {
  return {
    record_count: 9,
    valid_comment_count: 9,
    unique_comment_count: 6,
    executable_count: 4,
    excluded_count: 2,
    blocked_count: 2,
    unknown_category_count: 2,
    unknown_categories: [],
    segments: [segment("合成阻断", "blocked"), segment("合成A"), segment("合成B")],
    ...changes,
  };
}

function cards() {
  return [...document.querySelectorAll(".plan-segments article")];
}

test("已保存顺序过滤失效键并补全分组，移动就绪分组后将阻断分组附在末尾", async () => {
  const user = userEvent.setup();
  const onSegmentOrderChange = vi.fn();
  render(
    <ExecutionPlanSummary
      plan={plan()}
      segmentOrder={["合成失效", "合成B", "合成阻断"]}
      onSegmentOrderChange={onSegmentOrderChange}
    />,
  );
  expect(cards().map((item) => item.querySelector("h4").textContent)).toEqual([
    "01 · 合成B",
    "合成阻断",
    "02 · 合成A",
  ]);
  expect(screen.getByRole("button", { name: "置顶 合成B" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "上移 合成B" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "下移 合成A" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "置顶 合成A" }));
  expect(onSegmentOrderChange).toHaveBeenCalledExactlyOnceWith([
    "合成A",
    "合成B",
    "合成阻断",
  ]);
  expect(cards()[1]).toHaveAttribute("draggable", "false");
});

test.each(["上移 合成B", "下移 合成A"])(
  "排序按钮只调整可执行队列：%s",
  async (name) => {
    const user = userEvent.setup();
    const onSegmentOrderChange = vi.fn();
    render(
      <ExecutionPlanSummary
        plan={plan()}
        onSegmentOrderChange={onSegmentOrderChange}
      />,
    );
    await user.click(screen.getByRole("button", { name }));
    expect(onSegmentOrderChange).toHaveBeenCalledExactlyOnceWith([
      "合成B",
      "合成A",
      "合成阻断",
    ]);
  },
);

test("拖放沿用文本键，阻断目标不接收移动，可执行目标只移动可执行分组", () => {
  const onSegmentOrderChange = vi.fn();
  render(
    <ExecutionPlanSummary plan={plan()} onSegmentOrderChange={onSegmentOrderChange} />,
  );
  const [blocked, first, second] = cards();
  const transfer = {
    setData: vi.fn(),
    getData: vi.fn(() => "合成B"),
    effectAllowed: "",
  };
  fireEvent.dragStart(second, { dataTransfer: transfer });
  expect(transfer.setData).toHaveBeenCalledExactlyOnceWith("text/plain", "合成B");
  expect(transfer.effectAllowed).toBe("move");
  expect(fireEvent.dragOver(blocked, { dataTransfer: transfer })).toBe(true);
  fireEvent.drop(blocked, { dataTransfer: transfer });
  expect(transfer.getData).not.toHaveBeenCalled();
  expect(onSegmentOrderChange).not.toHaveBeenCalled();
  expect(fireEvent.dragOver(first, { dataTransfer: transfer })).toBe(false);
  fireEvent.drop(first, { dataTransfer: transfer });
  expect(transfer.getData).toHaveBeenCalledExactlyOnceWith("text/plain");
  expect(onSegmentOrderChange).toHaveBeenCalledExactlyOnceWith([
    "合成B",
    "合成A",
    "合成阻断",
  ]);
});

test("没有排序回调或仅一个可执行分组时不显示排序按钮", () => {
  const view = render(<ExecutionPlanSummary plan={plan()} />);
  expect(
    screen.queryByRole("button", { name: /置顶|上移|下移/ }),
  ).not.toBeInTheDocument();
  expect(cards().every((item) => item.getAttribute("draggable") === "false")).toBe(
    true,
  );
  view.rerender(
    <ExecutionPlanSummary
      plan={plan({ segments: [segment("合成A"), segment("合成阻断", "blocked")] })}
      onSegmentOrderChange={vi.fn()}
    />,
  );
  expect(
    screen.queryByRole("button", { name: /置顶|上移|下移/ }),
  ).not.toBeInTheDocument();
});

test("紧凑模式在原生折叠中保留分组、标准、范围和品类显示", async () => {
  const user = userEvent.setup();
  const value = plan();
  value.segments[1] = {
    ...value.segments[1],
    scope: { store: "合成店铺", listing: "合成Listing" },
    standard_name: "合成标准",
    standard_version: 7,
    logic_version: "合成逻辑",
  };
  render(<ExecutionPlanSummary plan={value} compact onSegmentOrderChange={vi.fn()} />);
  expect(screen.getByText("查看 3 个执行分组及顺序")).toBeVisible();
  await user.click(screen.getByText("查看 3 个执行分组及顺序"));
  expect(
    screen.getByRole("heading", { name: "01 · 合成Listing · 合成标准" }),
  ).toBeVisible();
  expect(
    screen.getByText(/合成店铺 \/ 合成Listing · 标准 V7 · logic 合成逻辑/),
  ).toBeVisible();
  expect(screen.getByRole("button", { name: "下移 合成Listing" })).toBeEnabled();
});

test("品类补齐提示显示商品与评论口径，保留补齐回调并隐藏重复排除操作", async () => {
  const user = userEvent.setup();
  const onResolveCategories = vi.fn();
  render(
    <ExecutionPlanSummary
      plan={plan({
        blocked_count: 0,
        category_completion_required: true,
        missing_category_count: 2,
        missing_category_product_count: 3,
        missing_category_comment_count: 5,
      })}
      onResolveCategories={onResolveCategories}
    />,
  );
  expect(screen.getByText("3 个商品缺少品类A或品类B，影响 5 条评论")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "处理排除原因" }),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "补齐商品品类" }));
  expect(onResolveCategories).toHaveBeenCalledOnce();
});

test("排除原因沿用数量和顺序，处理按钮使用既有修复回调", async () => {
  const user = userEvent.setup();
  const onResolveCategories = vi.fn();
  render(
    <ExecutionPlanSummary
      plan={plan({
        blocked_count: 0,
        unmatched_product_count: 1,
        missing_category_count: 2,
        unknown_category_count: 3,
        unresolved_scope_count: 4,
      })}
      onResolveCategories={onResolveCategories}
    />,
  );
  expect(
    screen.getByText(
      /原因：产品信息未匹配 1 组；缺失品类 2 组；未配置分类逻辑 3 组；范围未识别 4 组。/,
    ),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "处理排除原因" }));
  expect(onResolveCategories).toHaveBeenCalledOnce();
});

test("阻断范围、商品修复和处理策略保留各自的动作", async () => {
  const user = userEvent.setup();
  const onResolveCategories = vi.fn();
  const onPolicyChange = vi.fn();
  render(
    <ExecutionPlanSummary
      plan={plan({
        unresolved_product_count: 2,
        unknown_categories: [
          { category_a: "合成未知A", category_b: "合成未知B", record_count: 2 },
        ],
      })}
      policy="block_all"
      onResolveCategories={onResolveCategories}
      onPolicyChange={onPolicyChange}
    />,
  );
  expect(screen.getByText("合成未知A / 合成未知B · 2 条")).toBeVisible();
  expect(screen.getByRole("radio", { name: /全部阻断/ })).toBeChecked();
  await user.click(screen.getByRole("radio", { name: /先运行已就绪/ }));
  expect(onPolicyChange).toHaveBeenCalledExactlyOnceWith("run_ready");
  await user.click(screen.getByRole("button", { name: "处理 2 个商品匹配异常" }));
  expect(onResolveCategories).toHaveBeenCalledOnce();
});

test.each([false, true])("数量不对账时保留警告和覆盖率，紧凑=%s", (compact) => {
  render(
    <ExecutionPlanSummary
      plan={plan({ unique_comment_count: 7 })}
      quality={{
        counts: { total_records: 9, matched_records: 3, unmatched_records: 6 },
      }}
      compact={compact}
    />,
  );
  expect(screen.getByText("评论数量口径未对齐")).toBeVisible();
  expect(screen.getByText(/可执行覆盖率 57.1%。/)).toBeVisible();
  if (!compact) expect(screen.getByText("33.33%")).toBeVisible();
});

test("紧凑且已对账时只显示原数量行，零匹配总数显示零百分比", () => {
  const value = plan({ blocked_count: 0, unknown_category_count: 0 });
  const view = render(<ExecutionPlanSummary plan={value} compact />);
  expect(screen.getByText("9 条用户反馈 · 9 条有文本 · 合并为 6 组评论")).toBeVisible();
  expect(screen.queryByText(/去重评论已对账/)).not.toBeInTheDocument();
  view.rerender(
    <ExecutionPlanSummary
      plan={value}
      quality={{ counts: { total_records: 0, matched_records: 0 } }}
    />,
  );
  expect(screen.getByText("0.00%")).toBeVisible();
  expect(screen.getByText("去重评论已对账：6 = 4 + 2")).toBeVisible();
});
