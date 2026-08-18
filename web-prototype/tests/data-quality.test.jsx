import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const { dataVersions, qualityPreflight, qualityIssues } = vi.hoisted(() => ({
  dataVersions: vi.fn(),
  qualityPreflight: vi.fn(),
  qualityIssues: vi.fn(),
}));

vi.mock("../src/shared/api/dataApi", () => ({
  dataApi: { dataVersions, qualityPreflight, qualityIssues },
}));

import { DataQualityPage } from "../src/features/data-management/DataQualityPage";

const versions = [
  {
    id: "returns-v2",
    dataset_name: "SEEKWAY 退货明细",
    kind: "returns",
    version: 2,
  },
  {
    id: "products-v1",
    dataset_name: "SEEKWAY 商品目录",
    kind: "products",
    version: 1,
  },
];

beforeEach(() => {
  dataVersions.mockReset().mockResolvedValue(versions);
  qualityPreflight.mockReset();
  qualityIssues.mockReset();
  window.location.hash = "";
});

afterEach(() => cleanup());

test("未选齐不可变版本对时不发质量请求也不展示旧统计", async () => {
  render(<DataQualityPage route={{ query: {} }} />);

  expect(await screen.findByRole("heading", { name: "数据资产" })).toBeVisible();
  expect(screen.getByText("请先选择完整版本对")).toBeVisible();
  expect(screen.queryByText("匹配成功")).not.toBeInTheDocument();
  expect(qualityPreflight).not.toHaveBeenCalled();
  expect(qualityIssues).not.toHaveBeenCalled();

  await userEvent.selectOptions(screen.getByLabelText("退货数据版本"), "returns-v2");
  expect(window.location.hash).toContain("returns_version_id=returns-v2");
});

test("质量页消费真实预检和问题分页并区分整数零值", async () => {
  qualityPreflight.mockResolvedValue({
    returns_version: { id: "returns-v2", name: "SEEKWAY 退货明细", version: 2 },
    products_version: { id: "products-v1", name: "SEEKWAY 商品目录", version: 1 },
    match_key: {
      returns: ["store_site", "sku"],
      products: ["store_site", "MSKU"],
    },
    counts: {
      total_records: 108397,
      matched_records: 108300,
      unmatched_records: 97,
      missing_store_records: 0,
      missing_source_sku_records: 1,
      missing_category_records: 12,
      missing_product_name_records: 3,
    },
    quality_hash: "quality-hash-1",
  });
  qualityIssues.mockResolvedValue({
    total: 1,
    page: 1,
    page_size: 20,
    items: [
      {
        issue_type: "missing_category",
        store_site: "SEEKWAY:US",
        source_sku: "MSKU-1",
        listing: "SR001",
        product_name: null,
        category_a: null,
        category_b: null,
        reason: "商品目录未提供品类",
        record_count: 12,
      },
    ],
  });

  render(
    <DataQualityPage
      route={{
        query: {
          returns_version_id: "returns-v2",
          products_version_id: "products-v1",
          issue_type: "missing_category",
          page: "1",
        },
      }}
    />,
  );

  expect(await screen.findByText("108,300")).toBeVisible();
  const missingStoreCard = screen
    .getAllByText("缺失店铺/站点")
    .map((node) => node.closest("article"))
    .find(Boolean);
  expect(within(missingStoreCard).getByText("0")).toBeVisible();
  expect(screen.getByText("商品目录未提供品类")).toBeVisible();
  expect(screen.getAllByText("未提供").length).toBeGreaterThan(0);
  expect(qualityPreflight).toHaveBeenCalledTimes(1);
  expect(qualityIssues).toHaveBeenCalledWith(
    expect.objectContaining({
      returns_version_id: "returns-v2",
      products_version_id: "products-v1",
      issue_type: "missing_category",
      page: 1,
      page_size: 20,
    }),
    expect.objectContaining({ signal: expect.anything() }),
  );
});

test("大型版本冷加载只发一次请求并保持明确稳定提示", async () => {
  qualityPreflight.mockReturnValue(new Promise(() => {}));
  qualityIssues.mockReturnValue(new Promise(() => {}));

  render(
    <DataQualityPage
      route={{
        query: {
          returns_version_id: "returns-v2",
          products_version_id: "products-v1",
        },
      }}
    />,
  );

  expect(
    (await screen.findAllByText(/首次读取大型版本可能需要数秒/)).length,
  ).toBeGreaterThan(0);
  expect(qualityPreflight).toHaveBeenCalledTimes(1);
  expect(qualityIssues).toHaveBeenCalledTimes(1);
});
