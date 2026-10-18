import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { renderWithServerState as render } from "./renderWithServerState";
import { afterEach, expect, test } from "vitest";
import { ProductMasterImpact } from "../src/features/data-management/ProductMasterImpact";

afterEach(() => cleanup());

test("产品修改记录保留原值新值、操作者、原因和批量补充范围", () => {
  const view = render(<ProductMasterImpact dimensionAudit={[]} />);
  expect(screen.getByText("尚无产品信息人工修改。")).toBeVisible();
  view.rerender(
    <ProductMasterImpact
      dimensionAudit={[
        {
          id: "row",
          action: "dimension_row_update",
          actor_name: "合成用户",
          created_at: "2026-10-13T01:00:00Z",
          before: { values: { 数量: 0 } },
          after: { row_index: 0, values: { 数量: 1 }, note: "合成修正原因" },
        },
        {
          id: "import",
          action: "product_update",
          actor_name: "合成管理员",
          before: { row_count: 10 },
          after: { row_count: 12, note: "合成更新原因" },
        },
        {
          id: "category",
          action: "dimension_category_completion",
          actor_name: "合成管理员",
          after: { store: "合成店铺", items: [{}, {}], note: "合成品类原因" },
        },
      ]}
    />,
  );
  expect(screen.queryByText("尚无产品信息人工修改。")).toBeNull();
  expect(screen.getByText("合成用户 · 修改第 2 行")).toBeVisible();
  expect(screen.getByText("0", { selector: "td" })).toBeVisible();
  expect(screen.getByText("1", { selector: "td" })).toBeVisible();
  expect(screen.getByText("修改原因：合成修正原因")).toBeVisible();
  expect(screen.getByText("10", { selector: "td" })).toBeVisible();
  expect(screen.getByText("12", { selector: "td" })).toBeVisible();
  expect(screen.getByText("合成管理员 · 批量补充 2 个商品")).toBeVisible();
  expect(screen.getByText("店铺：合成店铺 · 品类补充")).toBeVisible();
});

test("产品行增量新值不把未变化字段误显示为清空", () => {
  render(
    <ProductMasterImpact
      dimensionAudit={[
        {
          id: "partial-product",
          action: "dimension_row_update",
          before: { values: { MSKU: "合成产品", Listing: "L1", 产品名称: "旧名称" } },
          after: { values: { 产品名称: "新名称" } },
        },
      ]}
    />,
  );
  expect(screen.getByText("字段变化 · 1 项")).toBeVisible();
  const table = screen.getAllByRole("table", { name: "字段差异" })[0];
  expect(within(table).getByText("旧名称")).toBeVisible();
  expect(within(table).getByText("新名称")).toBeVisible();
  expect(within(table).queryByText("MSKU")).toBeNull();
  expect(within(table).queryByText("未提供")).toBeNull();
});

test("品类补充按店铺与 MSKU 配对前后值，区分新增和多行商品", () => {
  render(
    <ProductMasterImpact
      dimensionAudit={[
        {
          id: "categories",
          action: "dimension_category_completion",
          before: {
            items: [
              {
                store: "店铺乙",
                msku: "同名SKU",
                rows: [2],
                category_a: "泳鞋",
                category_b: "厚底",
              },
              {
                store: "店铺甲",
                msku: "同名SKU",
                rows: [0, 1],
                category_a: "水鞋",
                category_b: "薄底",
              },
              { store: "店铺甲", msku: "新增SKU", rows: [] },
            ],
          },
          after: {
            items: [
              {
                store: "店铺甲",
                msku: "同名SKU",
                category_a: "户外鞋",
                category_b: "防滑",
              },
              {
                store: "店铺乙",
                msku: "同名SKU",
                category_a: "水鞋",
                category_b: "柔软",
              },
              {
                store: "店铺甲",
                msku: "新增SKU",
                category_a: "凉鞋",
                category_b: "露趾",
              },
            ],
          },
        },
      ]}
    />,
  );
  const first = screen.getByText("店铺：店铺甲 · MSKU：同名SKU", { exact: true });
  fireEvent.click(first);
  const firstDetail = first.closest("details");
  expect(within(firstDetail).getByText("水鞋")).toBeVisible();
  expect(within(firstDetail).getByText("户外鞋")).toBeVisible();
  expect(within(firstDetail).queryByText("泳鞋")).not.toBeInTheDocument();
  expect(within(firstDetail).getByText(/本次关联 2 行/)).toBeVisible();
  const second = screen.getByText("店铺：店铺乙 · MSKU：同名SKU", { exact: true });
  fireEvent.click(second);
  expect(within(second.closest("details")).getByText("泳鞋")).toBeVisible();
  const added = screen.getByText("店铺：店铺甲 · MSKU：新增SKU · 新增商品", {
    exact: true,
  });
  fireEvent.click(added);
  const table = within(added.closest("details")).getByRole("table", {
    name: "字段差异",
  });
  expect(within(table).getAllByText("新增商品")).toHaveLength(2);
  expect(within(table).getByText("凉鞋")).toBeVisible();
});

test("旧品类日志缺少原值时明确未记录，不推断新增商品", () => {
  render(
    <ProductMasterImpact
      dimensionAudit={[
        {
          id: "legacy",
          action: "dimension_category_completion",
          after: {
            store: "合成店铺",
            items: [{ msku: "旧SKU", category_a: "水鞋", category_b: "薄底" }],
          },
        },
      ]}
    />,
  );
  const summary = screen.getByText("店铺：合成店铺 · MSKU：旧SKU", { exact: true });
  fireEvent.click(summary);
  const detail = within(summary.closest("details"));
  expect(detail.getAllByText("未记录")).toHaveLength(2);
  expect(detail.getByText("水鞋")).toBeVisible();
  expect(screen.queryByText(/新增商品/)).not.toBeInTheDocument();
});

test.each([undefined, [], [{}]])("旧品类日志缺失明细时不编造变化 %#", (items) => {
  render(
    <ProductMasterImpact
      dimensionAudit={[
        {
          id: "missing",
          action: "dimension_category_completion",
          after: { items },
        },
      ]}
    />,
  );
  expect(
    screen.queryByRole("table", { name: "字段差异", hidden: true }),
  ).not.toBeInTheDocument();
  if (items?.length) {
    fireEvent.click(screen.getByText("店铺：未记录 · MSKU：未记录", { exact: true }));
    expect(screen.getByText("未记录品类明细，无法展示前后变化。")).toBeVisible();
  } else {
    expect(screen.getByText("未记录商品明细。")).toBeVisible();
  }
});
