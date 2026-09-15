import { describe, expect, test } from "vitest";

import {
  buildInitialProductMatchDrafts,
  buildProductCategoryOptions,
  buildProductMatchGroups,
  buildProductMatchSaveItems,
  productMatchKey,
} from "../src/features/task-create/productMatchPolicy";

describe("商品匹配策略", () => {
  test("按店铺和 Listing 分组并仅将信息完整的分组判定为就绪", () => {
    const items = [
      {
        product_key: "sku-1",
        store: "US",
        msku: "sku-1",
        suggested_listing: "LISTING-A",
        comment_count: 2,
        record_count: 3,
        editable: true,
        match_status: "high_confidence",
        match_candidate: {
          listing: "LISTING-A",
          category_a: "鞋履",
          category_b: "水鞋",
        },
      },
      {
        product_key: "sku-2",
        store: "US",
        msku: "sku-2",
        suggested_listing: "LISTING-A",
        comment_count: 5,
        record_count: 6,
        editable: true,
        match_status: "needs_review",
      },
    ];
    const drafts = buildInitialProductMatchDrafts(items);
    const groups = buildProductMatchGroups(items, drafts);

    expect(groups).toHaveLength(1);
    expect(groups[0]).toMatchObject({
      commentCount: 7,
      recordCount: 9,
      matchedCount: 1,
      needsReview: 1,
      ready: false,
      categoryLabel: "鞋履 > 水鞋",
    });
  });

  test("保存输出仅包含 API 需要的商品草稿结构", () => {
    const items = [
      {
        product_key: "sku-1",
        store: "CA",
        msku: "sku-1",
        suggested_listing: "LISTING-B",
        editable: true,
        match_status: "high_confidence",
        match_candidate: {
          listing: "LISTING-B",
          category_a: "服饰",
          category_b: "雨衣",
          product_name: "商品一",
        },
      },
    ];
    const drafts = buildInitialProductMatchDrafts(items);
    const groups = buildProductMatchGroups(items, drafts);

    expect(buildProductMatchSaveItems(groups, drafts)).toEqual([
      {
        store: "CA",
        msku: "sku-1",
        listing: "LISTING-B",
        category_a: "服饰",
        category_b: "雨衣",
        product_name: "商品一",
      },
    ]);
    expect(productMatchKey(items[0])).toBe("CA\u001fsku-1");
  });

  test("品类选项保留原始 B 类顺序并对 A 类去重排序", () => {
    expect(
      buildProductCategoryOptions([
        { category_a: "鞋履", category_b: "厚底水鞋" },
        { category_a: "服饰", category_b: "雨衣" },
        { category_a: "鞋履", category_b: "薄底水鞋" },
      ]),
    ).toEqual({
      categoryAs: ["服饰", "鞋履"],
      categoryBsByA: {
        服饰: ["雨衣"],
        鞋履: ["厚底水鞋", "薄底水鞋"],
      },
    });
  });
});
