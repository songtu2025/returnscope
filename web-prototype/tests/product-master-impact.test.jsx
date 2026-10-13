import { cleanup, screen } from "@testing-library/react";
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
