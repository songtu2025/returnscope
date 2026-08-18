import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    classificationResults: vi.fn(),
    classificationResultDownloadUrl: vi.fn(),
  },
}));

vi.mock("../src/api", () => ({ api: apiMock }));

import { ClassificationResultsPage } from "../src/pages/ClassificationResultsPage";

const resultVersion = {
  version_id: "classification-version-qa",
  version: 1,
  quality_status: "ready",
  publish_status: "published",
  store_site: "SEEKWAY:US",
  listing: "SR001",
  product_names: ["产品表名称"],
  record_count: 12,
  unit_count: 8,
  product_version: 3,
};

function resultPage(overrides = {}) {
  return {
    items: [resultVersion],
    total: 120,
    page: 1,
    page_size: 20,
    ...overrides,
  };
}

beforeEach(() => {
  window.location.hash = "classification-results";
  Object.values(apiMock).forEach((mock) => mock.mockReset());
  apiMock.classificationResultDownloadUrl.mockImplementation(
    (id) => `/api/classification-results/${id}/download`,
  );
});

afterEach(() => cleanup());

test("列表筛选和分页可从 URL 恢复并继续稳定翻页", async () => {
  const user = userEvent.setup();
  window.location.hash =
    "classification-results?page=2&page_size=50&q=%E6%B0%B4%E9%9E%8B&store_site=SEEKWAY%3AUS&listing=SR001&quality_status=ready";
  apiMock.classificationResults.mockResolvedValue(
    resultPage({ page: 2, page_size: 50 }),
  );

  render(<ClassificationResultsPage notify={vi.fn()} />);

  expect(await screen.findByText("产品表名称")).toBeVisible();
  await waitFor(() =>
    expect(apiMock.classificationResults).toHaveBeenCalledWith(
      {
        page: 2,
        page_size: 50,
        q: "水鞋",
        store_site: "SEEKWAY:US",
        listing: "SR001",
        quality_status: "ready",
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ),
  );
  expect(screen.getByRole("textbox", { name: "搜索分类结果" })).toHaveValue("水鞋");

  await user.click(screen.getByRole("button", { name: "下一页" }));

  await waitFor(() =>
    expect(apiMock.classificationResults).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 3, page_size: 50, q: "水鞋" }),
      expect.any(Object),
    ),
  );
  expect(window.location.hash).toContain("page=3");
});

test("q 输入显式提交且替换查询会取消旧请求", async () => {
  const user = userEvent.setup();
  let firstSignal;
  apiMock.classificationResults
    .mockImplementationOnce((_filters, options) => {
      firstSignal = options.signal;
      return new Promise(() => {});
    })
    .mockResolvedValue(resultPage());

  render(<ClassificationResultsPage notify={vi.fn()} />);
  await waitFor(() => expect(firstSignal).toBeInstanceOf(AbortSignal));

  await user.type(
    screen.getByRole("textbox", { name: "搜索分类结果" }),
    "PRODUCT-SKU-1",
  );
  expect(apiMock.classificationResults).toHaveBeenCalledTimes(1);

  await user.click(screen.getByRole("button", { name: "筛选" }));

  await waitFor(() => expect(apiMock.classificationResults).toHaveBeenCalledTimes(2));
  expect(firstSignal.aborted).toBe(true);
});
