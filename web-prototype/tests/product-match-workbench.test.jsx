import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { ProductMatchWorkbench } from "../src/features/task-create/ProductMatchWorkbench";

afterEach(cleanup);

function buildPlan() {
  return {
    unresolved_product_comment_count: 17,
    category_options: [
      { category_a: "鞋履", category_b: "水鞋" },
      { category_a: "服饰", category_b: "雨衣" },
    ],
    unresolved_products: [
      {
        product_key: "alpha-1",
        store: "US",
        msku: "alpha-1",
        suggested_listing: "ALPHA",
        comment_count: 8,
        record_count: 9,
        editable: true,
        match_status: "high_confidence",
        match_candidate: {
          msku: "alpha-source-1",
          listing: "ALPHA",
          category_a: "鞋履",
          category_b: "水鞋",
          product_name: "Alpha 一号",
          match_score: 100,
        },
      },
      {
        product_key: "alpha-2",
        store: "US",
        msku: "alpha-2",
        suggested_listing: "ALPHA",
        comment_count: 4,
        record_count: 4,
        editable: true,
        match_status: "high_confidence",
        match_candidate: {
          msku: "alpha-source-2",
          listing: "ALPHA",
          category_a: "鞋履",
          category_b: "水鞋",
          product_name: "Alpha 二号",
          match_score: 100,
        },
      },
      {
        product_key: "beta-1",
        store: "CA",
        msku: "beta-1",
        suggested_listing: "BETA",
        comment_count: 5,
        record_count: 6,
        editable: true,
        match_status: "needs_review",
        match_candidate: {
          msku: "beta-source-1",
          listing: "BETA",
          category_a: "鞋履",
          category_b: "水鞋",
          product_name: "Beta 一号",
          match_score: 80,
        },
      },
    ],
  };
}

function renderWorkbench(onSave = vi.fn()) {
  render(
    <ProductMatchWorkbench
      plan={buildPlan()}
      saving={false}
      onBack={vi.fn()}
      onSave={onSave}
    />,
  );
  return onSave;
}

function listingGroup(listing) {
  return screen.getByText(listing, { selector: "b" }).closest("article");
}

describe("商品匹配工作台", () => {
  test("编辑商品后只使对应分组的旧确认失效", async () => {
    const user = userEvent.setup();
    renderWorkbench();
    const alphaGroup = listingGroup("ALPHA");
    const betaGroup = listingGroup("BETA");

    await user.click(within(alphaGroup).getByRole("button", { name: "确认关联" }));
    await user.click(within(betaGroup).getByRole("button", { name: "确认关联" }));
    expect(within(alphaGroup).getByText("已确认")).toBeVisible();
    expect(within(betaGroup).getByText("已确认")).toBeVisible();

    await user.clear(screen.getByLabelText("US alpha-1 Listing"));
    await user.type(screen.getByLabelText("US alpha-1 Listing"), "ALPHA-NEW");

    expect(within(alphaGroup).getByText("待处理")).toBeVisible();
    expect(within(betaGroup).getByText("已确认")).toBeVisible();
  });

  test("批量修改仅影响已选商品并清空相应分组确认", async () => {
    const user = userEvent.setup();
    const onSave = renderWorkbench();
    const alphaGroup = listingGroup("ALPHA");
    const betaGroup = listingGroup("BETA");

    await user.click(within(alphaGroup).getByRole("button", { name: "确认关联" }));
    await user.click(within(betaGroup).getByRole("button", { name: "确认关联" }));
    await user.click(screen.getByLabelText("选择商品 US alpha-1"));
    await user.selectOptions(screen.getByLabelText("批量品类A"), "服饰");
    await user.selectOptions(screen.getByLabelText("批量品类B"), "雨衣");
    await user.click(screen.getByRole("button", { name: "应用到 1 个商品" }));

    expect(
      screen.getByText("已选择 0 个销售 SKU；应用后需重新确认对应 Listing。"),
    ).toBeVisible();
    expect(within(alphaGroup).getByText("待处理")).toBeVisible();
    expect(within(betaGroup).getByText("已确认")).toBeVisible();

    await user.click(within(alphaGroup).getByRole("button", { name: "确认关联" }));
    await user.click(screen.getByRole("button", { name: "保存关联并重新生成计划" }));
    expect(onSave).toHaveBeenCalledWith([
      expect.objectContaining({
        msku: "alpha-1",
        category_a: "服饰",
        category_b: "雨衣",
      }),
      expect.objectContaining({
        msku: "alpha-2",
        category_a: "鞋履",
        category_b: "水鞋",
      }),
      expect.objectContaining({
        msku: "beta-1",
        category_a: "鞋履",
        category_b: "水鞋",
      }),
    ]);
  });

  test("筛选、展开和确认交互保持原有语义", async () => {
    const user = userEvent.setup();
    renderWorkbench();

    expect(screen.getByRole("tab", { name: "高匹配建议（1）" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "需人工确认（1）" })).toBeVisible();
    expect(screen.getByRole("button", { name: /ALPHA/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );

    const reviewTab = screen.getByRole("tab", { name: "需人工确认（1）" });
    reviewTab.focus();
    await user.keyboard("{Enter}");
    expect(reviewTab).toHaveFocus();
    expect(reviewTab).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByText("ALPHA", { selector: "b" })).not.toBeInTheDocument();
    expect(screen.getByText("BETA", { selector: "b" })).toBeVisible();
    const betaToggle = screen.getByRole("button", { name: /BETA/ });
    expect(betaToggle).toHaveAttribute("aria-expanded", "false");

    await user.click(betaToggle);
    expect(betaToggle).toHaveAttribute("aria-expanded", "true");
    const betaGroup = listingGroup("BETA");
    await user.click(within(betaGroup).getByRole("button", { name: "确认关联" }));
    expect(within(betaGroup).getByText("已确认")).toBeVisible();
  });
});
