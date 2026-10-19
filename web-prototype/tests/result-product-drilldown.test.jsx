import { act, cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { renderWithServerState as render } from "./renderWithServerState";
const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    classificationResultDrilldown: vi.fn(),
    classificationResultRecordGroups: vi.fn(),
  },
}));
vi.mock("../src/api", () => ({ api: apiMock }));
import { ResultProductDrilldown } from "../src/features/classification-results/ResultProductDrilldown";
import { classificationResultRouteState } from "../src/features/classification-results/classificationResultRoute";
import {
  readResultRecords,
  resultRecordQuery,
} from "../src/features/classification-results/classificationResultReads";

const items = Array.from({ length: 198 }, (_, index) => ({
  value: `SKU-${String(index + 1).padStart(3, "0")}`,
  record_count: 1,
  unit_count: 1,
}));
const route = classificationResultRouteState({
  result_version_id: "synthetic",
  problem: "FIT",
  product_name: "产品甲",
});
const props = {
  route,
  groupBy: "product_sku",
  title: "产品SKU",
  items: items.slice(0, 12),
  total: 198,
  selected: "SKU-101",
  onSelect: vi.fn(),
};
beforeEach(() => {
  vi.clearAllMocks();
  Element.prototype.scrollTo = vi.fn();
  apiMock.classificationResultDrilldown.mockImplementation(
    async (_version, groupBy, { page, page_size }) => {
      const values = groupBy === "product_name" ? items.slice(0, 23) : items;
      return {
        items: values.slice((page - 1) * page_size, page * page_size),
        total: values.length,
        page,
        page_size,
        group_by: groupBy,
      };
    },
  );
});
afterEach(cleanup);

test("快捷12项不额外请求，完整分页可选择第101项且不丢其他页已选值", async () => {
  render(<ResultProductDrilldown {...props} />);
  expect(screen.getAllByRole("button", { name: /SKU-\d/ })).toHaveLength(12);
  expect(screen.getByText("当前选中：SKU-101")).toBeVisible();
  expect(apiMock.classificationResultDrilldown).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "查看全部产品SKU" }));
  await screen.findByRole("button", { name: /SKU-020\s*1 组/ });
  for (let page = 2; page <= 6; page++) {
    await userEvent.click(screen.getByRole("button", { name: "下一页" }));
    await screen.findByRole("button", {
      name: new RegExp(`SKU-${String((page - 1) * 20 + 1).padStart(3, "0")}\\s*1 组`),
    });
  }
  expect(apiMock.classificationResultDrilldown).toHaveBeenLastCalledWith(
    "synthetic",
    "product_sku",
    { page: 6, page_size: 20, problem: "FIT", product_name: "产品甲" },
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
  );
  await userEvent.click(screen.getByRole("button", { name: /SKU-101\s*1 组/ }));
  expect(props.onSelect).toHaveBeenCalledExactlyOnceWith("SKU-101");
  await userEvent.click(screen.getByRole("button", { name: "收起全部" }));
  expect(screen.getByText("当前选中：SKU-101")).toBeVisible();
  expect(screen.queryByRole("button", { name: /SKU-101\s*1 组/ })).toBeNull();
});

test("完整产品列表包含第13项与第二页，问题范围始终传入", async () => {
  render(
    <ResultProductDrilldown
      {...props}
      groupBy="product_name"
      title="产品名称"
      total={23}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "查看全部产品名称" }));
  await userEvent.click(await screen.findByRole("button", { name: /SKU-013\s*1 组/ }));
  await userEvent.click(screen.getByRole("button", { name: "下一页" }));
  await screen.findByRole("button", { name: /SKU-023\s*1 组/ });
  expect(apiMock.classificationResultDrilldown).toHaveBeenLastCalledWith(
    "synthetic",
    "product_name",
    { page: 2, page_size: 20, problem: "FIT" },
    expect.any(Object),
  );
});

test("加载不冒充空态，错误保留范围并手动重试，空结果仍可收起", async () => {
  let reject;
  apiMock.classificationResultDrilldown.mockImplementationOnce(
    () =>
      new Promise((_resolve, fail) => {
        reject = fail;
      }),
  );
  render(<ResultProductDrilldown {...props} />);
  await userEvent.click(screen.getByRole("button", { name: "查看全部产品SKU" }));
  expect(await screen.findByText("正在读取产品SKU…")).toBeVisible();
  expect(screen.queryByText("暂无数据")).toBeNull();
  await act(async () => reject(new Error("合成候选读取失败")));
  expect(await screen.findByRole("alert")).toHaveTextContent("合成候选读取失败");
  apiMock.classificationResultDrilldown.mockResolvedValueOnce({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
  });
  await userEvent.click(screen.getByRole("button", { name: "重新读取产品SKU" }));
  await screen.findByText("暂无数据");
  await userEvent.click(screen.getByRole("button", { name: "收起全部" }));
  expect(screen.getByRole("button", { name: "查看全部产品SKU" })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
});

test.each(["problem", "productName", "version"])(
  "上级 %s 变化取消旧请求并重置快捷列表",
  async (key) => {
    let finish;
    apiMock.classificationResultDrilldown.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const view = render(<ResultProductDrilldown {...props} />);
    await userEvent.click(screen.getByRole("button", { name: "查看全部产品SKU" }));
    await waitFor(() => expect(finish).toBeTypeOf("function"));
    const signal = apiMock.classificationResultDrilldown.mock.calls[0][3].signal;
    view.rerender(
      <ResultProductDrilldown
        {...props}
        route={{ ...route, [key]: "new-scope" }}
        items={[]}
        total={0}
        selected=""
      />,
    );
    expect(signal.aborted).toBe(true);
    await act(async () =>
      finish({ items: [items[100]], total: 198, page: 1, page_size: 20 }),
    );
    expect(screen.queryByRole("button", { name: /SKU-101\s*1 组/ })).toBeNull();
    expect(screen.getByText("共 0 项")).toBeVisible();
  },
);

test("快捷读取保留完整总数，产品和SKU只请求12项，问题范围不变", async () => {
  apiMock.classificationResultRecordGroups.mockResolvedValue({ items: [], total: 0 });
  const result = await readResultRecords("synthetic", resultRecordQuery(route));
  expect(result.drilldowns.product_sku).toHaveLength(12);
  expect(result.drilldowns.totals).toEqual({ product_name: 23, product_sku: 198 });
  expect(apiMock.classificationResultDrilldown).toHaveBeenCalledWith(
    "synthetic",
    "problem",
    { page: 1, page_size: 100 },
    {},
  );
});
