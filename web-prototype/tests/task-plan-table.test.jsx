import { useState } from "react";
import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ExecutionPlanSummary } from "../src/features/task-planning/ExecutionPlanSummary";
import { renderWithServerState as render } from "./renderWithServerState";

afterEach(cleanup);
const segments = Array.from({ length: 4 }, (_, index) => ({
  segment_key: `key-${index}`,
  scope: { store: "合成店铺", listing: `DEMO-${index}` },
  agent_family: "合成标准",
  status: "ready",
  record_count: 2,
  unique_comments: 1,
  variants: [{ category_a: "合成品类", category_b: index % 2 ? "隐藏类" : "可见类" }],
}));
const plan = {
  plan_hash: "hash",
  segments,
  record_count: 8,
  valid_comment_count: 8,
  unique_comment_count: 4,
  executable_count: 4,
  excluded_count: 0,
  blocked_count: 0,
  unknown_categories: [],
};
function Harness({ value = plan }) {
  const [order, setOrder] = useState(value.segments.map((item) => item.segment_key));
  const [keys, setKeys] = useState(order);
  return (
    <ExecutionPlanSummary
      plan={value}
      segmentOrder={order}
      onSegmentOrderChange={setOrder}
      segmentSelection={{ keys, onChange: setKeys }}
    />
  );
}
const rowOrder = () =>
  [...document.querySelectorAll(".plan-segments tbody h4")].map(
    (item) => item.textContent,
  );

function pagedPlan() {
  const items = Array.from({ length: 23 }, (_, index) => ({
    ...segments[0],
    segment_key: `page-${index}`,
    scope: { store: "合成店铺", listing: `PAGE-${index}` },
  }));
  items.splice(20, 0, {
    ...items[19],
    segment_key: "page-19-extra",
    agent_family: "另一品类标准",
  });
  return { ...plan, segments: items, unique_comment_count: 24, executable_count: 24 };
}

test("按Listing分页不拆分同Listing分组，选择跨页保留且全范围操作不受分页限制", async () => {
  const user = userEvent.setup();
  render(<Harness value={pagedPlan()} />);
  expect(rowOrder()).toHaveLength(21);
  expect(
    screen.getAllByRole("checkbox", { name: "参与分析：PAGE-19", exact: true }),
  ).toHaveLength(2);
  await user.click(screen.getByRole("checkbox", { name: "本页全部参与" }));
  expect(screen.getByText("已选 3 / 23 个 Listing · 3 组待分析评论")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "下一页" }));
  expect(rowOrder()).toEqual(["PAGE-20", "PAGE-21", "PAGE-22"]);
  expect(screen.getByRole("checkbox", { name: "本页全部参与" })).toBeChecked();
  await user.click(
    screen.getByRole("checkbox", { name: "参与分析：PAGE-20", exact: true }),
  );
  await user.click(screen.getByRole("button", { name: "上一页" }));
  expect(
    screen.getByRole("checkbox", { name: "参与分析：PAGE-0", exact: true }),
  ).not.toBeChecked();
  await user.click(screen.getByRole("button", { name: "全部范围参与" }));
  expect(screen.getByText("已选 23 / 23 个 Listing · 24 组待分析评论")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "全部范围不参与" }));
  expect(screen.getByText("已选 0 / 23 个 Listing · 0 组待分析评论")).toBeVisible();
});

test("第二页搜索回首页，筛选范围选择保留筛选外项目，页容量按Listing计数", async () => {
  const user = userEvent.setup();
  render(<Harness value={pagedPlan()} />);
  await user.click(screen.getByRole("button", { name: "下一页" }));
  await user.type(screen.getByLabelText("搜索执行分组"), "PAGE-1");
  expect(
    screen.getByRole("navigation", { name: "分页，第 1 页，共 1 页" }),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "全部筛选结果不参与" }));
  expect(screen.getByText("已选 12 / 23 个 Listing · 12 组待分析评论")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "清除筛选" }));
  await user.click(screen.getByRole("button", { name: "下一页" }));
  expect(
    screen.getByRole("checkbox", { name: "参与分析：PAGE-20", exact: true }),
  ).toBeChecked();
  await user.click(screen.getByRole("combobox", { name: "每页数量" }));
  await user.click(await screen.findByRole("option", { name: "50 个 Listing/页" }));
  expect(rowOrder()).toHaveLength(24);
  expect(
    screen.getByRole("navigation", { name: "分页，第 1 页，共 1 页" }),
  ).toBeVisible();
});

test("第二页指定排序位置使用完整筛选队列编号，跨页移动不改变选择", async () => {
  const user = userEvent.setup();
  render(<Harness value={pagedPlan()} />);
  await user.click(screen.getByRole("button", { name: "下一页" }));
  await user.click(screen.getByRole("button", { name: "调整执行顺序" }));
  const row = screen
    .getByRole("heading", { name: "PAGE-22", exact: true })
    .closest("tr");
  await user.click(within(row).getByText("移至位置"));
  await user.type(screen.getByLabelText("移动 PAGE-22 到位置"), "1");
  await user.click(within(row).getByRole("button", { name: "移动", exact: true }));
  await user.click(screen.getByRole("button", { name: "上一页" }));
  expect(rowOrder()[0]).toBe("PAGE-22");
  expect(screen.getByText("已选 23 / 23 个 Listing · 24 组待分析评论")).toBeVisible();
});

test("搜索、品类筛选和清除只改变显示，表头选择只作用于可见Listing", async () => {
  const user = userEvent.setup();
  render(<Harness />);
  expect(screen.queryByRole("button", { name: "置顶 DEMO-0" })).not.toBeInTheDocument();
  await user.selectOptions(
    screen.getByLabelText("按分组品类筛选"),
    "合成品类 / 可见类",
  );
  expect(rowOrder()).toEqual(["DEMO-0", "DEMO-2"]);
  expect(screen.getByText("已选 4 / 4 个 Listing · 4 组待分析评论")).toBeVisible();
  await user.click(screen.getByRole("checkbox", { name: "本页全部参与" }));
  expect(screen.getByText("已选 2 / 4 个 Listing · 2 组待分析评论")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "清除筛选" }));
  expect(screen.getByRole("checkbox", { name: "参与分析：DEMO-1" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "参与分析：DEMO-0" })).not.toBeChecked();
  await user.type(screen.getByLabelText("搜索执行分组"), "NOT-FOUND");
  expect(screen.getByText("未找到匹配分组，请调整筛选条件。")).toBeVisible();
  expect(screen.getByRole("checkbox", { name: "本页全部参与" })).toBeDisabled();
  await user.clear(screen.getByLabelText("搜索执行分组"));
  await user.type(screen.getByLabelText("搜索执行分组"), "demo-2");
  expect(rowOrder()).toEqual(["DEMO-2"]);
});

test("筛选后上移只替换可见槽位，隐藏项相对顺序和选择不变；可恢复完整默认顺序", async () => {
  const user = userEvent.setup();
  render(<Harness />);
  await user.click(screen.getByRole("button", { name: "调整执行顺序" }));
  await user.selectOptions(
    screen.getByLabelText("按分组品类筛选"),
    "合成品类 / 可见类",
  );
  await user.click(screen.getByRole("button", { name: "上移 DEMO-2" }));
  expect(rowOrder()).toEqual(["DEMO-2", "DEMO-0"]);
  await user.click(screen.getByRole("button", { name: "清除筛选" }));
  expect(rowOrder()).toEqual(["DEMO-2", "DEMO-1", "DEMO-0", "DEMO-3"]);
  await user.click(screen.getByRole("button", { name: "恢复全部默认顺序" }));
  expect(rowOrder()).toEqual(["DEMO-0", "DEMO-1", "DEMO-2", "DEMO-3"]);
  expect(screen.getByRole("checkbox", { name: "本页全部参与" })).toBeChecked();
});

test("指定位置校验整数与范围，移动后编号和顺序一致", async () => {
  const user = userEvent.setup();
  render(<Harness />);
  await user.click(screen.getByRole("button", { name: "调整执行顺序" }));
  const row = screen.getByRole("heading", { name: "DEMO-0" }).closest("tr");
  await user.click(within(row).getByText("移至位置"));
  await user.type(screen.getByLabelText("移动 DEMO-0 到位置"), "99");
  await user.click(within(row).getByRole("button", { name: "移动", exact: true }));
  expect(within(row).getByRole("alert")).toHaveTextContent("请输入1到4的整数");
  await user.clear(screen.getByLabelText("移动 DEMO-0 到位置"));
  await user.type(screen.getByLabelText("移动 DEMO-0 到位置"), "3");
  await user.click(within(row).getByRole("button", { name: "移动", exact: true }));
  expect(rowOrder()).toEqual(["DEMO-1", "DEMO-2", "DEMO-0", "DEMO-3"]);
  expect(row.cells[1]).toHaveTextContent("03");
});

test("阻断筛选保留选择，并且没有执行排序按钮", async () => {
  const user = userEvent.setup();
  render(
    <ExecutionPlanSummary
      plan={{ ...plan, segments: [{ ...segments[0], status: "blocked" }] }}
      onSegmentOrderChange={vi.fn()}
    />,
  );
  await user.selectOptions(screen.getByLabelText("按分组执行状态筛选"), "blocked");
  expect(rowOrder()).toEqual(["DEMO-0"]);
  expect(
    screen.queryByRole("button", { name: /置顶|上移|下移/ }),
  ).not.toBeInTheDocument();
});

test("筛选排序保留隐藏阻断项和隐藏可执行项之间的相对顺序", async () => {
  const user = userEvent.setup();
  render(
    <Harness
      value={{
        ...plan,
        segments: [
          segments[0],
          { ...segments[1], status: "blocked" },
          segments[2],
          segments[3],
        ],
      }}
    />,
  );
  await user.click(screen.getByRole("button", { name: "调整执行顺序" }));
  await user.selectOptions(
    screen.getByLabelText("按分组品类筛选"),
    "合成品类 / 可见类",
  );
  await user.click(screen.getByRole("button", { name: "上移 DEMO-2" }));
  await user.click(screen.getByRole("button", { name: "清除筛选" }));
  expect(rowOrder()).toEqual(["DEMO-2", "DEMO-1", "DEMO-0", "DEMO-3"]);
});
