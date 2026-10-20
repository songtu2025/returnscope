import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api";
import { renderWithServerState as render } from "./renderWithServerState";
import { DataAssetsPage } from "../src/features/data-management/DataAssetsPage";
import { buildHash, parseHash, useHashRoute } from "../src/app/hashRouter";
import {
  productAuditQuery,
  productAuditReturnQuery,
} from "../src/features/data-management/productAuditRoute";

const source = {
  view: "products",
  dataset: "products",
  tab: "impact",
  rows_q: "原查询",
  rows_store: "OLD:US",
  rows_category: "旧品类",
  rows_page: "4",
  rows_page_size: "50",
  reference_page: "3",
  result_return: "#classification-results?result_version_id=historical",
};
const item = {
  store: "DEMO:US",
  msku: "SAME",
  category_a: "鞋履",
  category_b: "当前品类",
};
const audit = {
  id: "audit-one",
  action: "dimension_category_completion",
  before: { items: [{ ...item, category_b: "旧品类" }] },
  after: { items: [item, { ...item, store: "DEMO:CA" }, { category_a: "标识缺失" }] },
};
const dataset = {
  id: "products",
  kind: "products",
  current_version: 3,
  version_id: "products-v3",
  row_count: 120,
  schema: [],
  audit: [audit],
};
const row = {
  _row_index: 9,
  MSKU: "SAME",
  "店铺/站点": "DEMO:US",
  Listing: "DEMO",
  产品名称: "当前产品",
};
function Harness() {
  const { route } = useHashRoute();
  return (
    <DataAssetsPage
      route={route}
      userId="proof-user"
      notify={vi.fn()}
      onNavigate={vi.fn()}
    />
  );
}
beforeEach(() => {
  window.history.replaceState({}, "", buildHash("data-assets", source));
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  vi.spyOn(api, "datasets").mockResolvedValue([dataset]);
  vi.spyOn(api, "dataset").mockResolvedValue(dataset);
  vi.spyOn(api, "datasetRows").mockResolvedValue({
    records: [row],
    total: 1,
    facets: { stores: ["DEMO:US"], categories: [] },
  });
  vi.spyOn(api, "dataVersionReferences").mockResolvedValue({ items: [], total: 0 });
  vi.spyOn(api, "updateDatasetRow");
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

async function openAudit() {
  render(<Harness />);
  const summary = await screen.findByText("店铺：DEMO:US · MSKU：SAME");
  await userEvent.click(summary);
  return within(summary.closest("details")).getByRole("button", {
    name: "查看当前产品",
  });
}

test("日志按店铺＋MSKU直达当前产品，返回保留原筛选、引用页、展开、滚动及焦点", async () => {
  const open = await openAudit();
  const scroll = vi.spyOn(window, "scrollY", "get").mockReturnValue(480);
  open.focus();
  await userEvent.keyboard("{Enter}");
  await screen.findByRole("button", { name: "编辑 SAME 产品信息" });
  expect(parseHash().query).toMatchObject({
    rows_q: "SAME",
    rows_store: "DEMO:US",
    rows_page: "1",
    rows_page_size: "50",
    tab: "rows",
  });
  expect(parseHash().query.rows_category).toBeUndefined();
  expect(api.datasetRows).toHaveBeenCalledWith("products", "SAME", 0, 50, {
    store: "DEMO:US",
    category: "",
  });
  expect(
    screen.queryByRole("button", { name: "查看当前产品" }),
  ).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "返回修改记录" }));
  await waitFor(() => expect(parseHash().query).toEqual(source));
  const returned = screen.getByText("店铺：DEMO:US · MSKU：SAME").closest("details");
  expect(api.datasetRows.mock.calls.every(([, q]) => q === "SAME")).toBe(true);
  expect(returned).toHaveAttribute("open");
  await waitFor(() =>
    expect(
      within(returned).getByRole("button", { name: "查看当前产品" }),
    ).toHaveFocus(),
  );
  expect(window.scrollTo).toHaveBeenLastCalledWith({
    top: 480,
    left: 0,
    behavior: "auto",
  });
  expect(screen.getByRole("button", { name: "返回分类结果" })).toBeVisible();
  expect(api.updateDatasetRow).not.toHaveBeenCalled();
  scroll.mockRestore();
});

test("返回修改记录仍保护未保存编辑，继续编辑保留输入，放弃才返回", async () => {
  await userEvent.click(await openAudit());
  await userEvent.click(
    await screen.findByRole("button", { name: "编辑 SAME 产品信息" }),
  );
  fireEvent.change(screen.getByLabelText("产品名称"), {
    target: { value: "保留输入" },
  });
  fireEvent.click(screen.getByRole("button", { name: "返回修改记录" }));
  expect(parseHash().query.tab).toBe("rows");
  fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
  expect(screen.getByLabelText("产品名称")).toHaveValue("保留输入");
  fireEvent.click(screen.getByRole("button", { name: "返回修改记录" }));
  fireEvent.click(screen.getByRole("button", { name: "放弃修改并离开" }));
  await waitFor(() => expect(parseHash().query).toEqual(source));
  expect(api.updateDatasetRow).not.toHaveBeenCalled();
});

test("当前资料已无此商品时显示既有空态，仍可返回原日志", async () => {
  api.datasetRows.mockResolvedValue({ records: [], total: 0 });
  await userEvent.click(await openAudit());
  expect(await screen.findByText("没有匹配的产品信息。")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "返回修改记录" }));
  await waitFor(() => expect(parseHash().query).toEqual(source));
});

test("单条修改采用变更后的商品标识，不按历史行号猜测", async () => {
  api.dataset.mockResolvedValue({
    ...dataset,
    audit: [
      {
        id: "row-audit",
        action: "dimension_row_update",
        before: { values: { MSKU: "BEFORE", "店铺/站点": "OLD:US" } },
        after: { row_index: 100, values: { MSKU: "AFTER", "店铺/站点": "DEMO:CA" } },
      },
    ],
  });
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "查看当前产品" }));
  expect(parseHash().query).toMatchObject({ rows_q: "AFTER", rows_store: "DEMO:CA" });
  expect(parseHash().query.row_index).toBeUndefined();
});

test("同名跨店铺分别定位，缺标识的日志不提供猜测入口", async () => {
  render(<Harness />);
  const summary = await screen.findByText("店铺：DEMO:CA · MSKU：SAME");
  await userEvent.click(summary);
  await userEvent.click(
    within(summary.closest("details")).getByRole("button", { name: "查看当前产品" }),
  );
  expect(parseHash().query.rows_store).toBe("DEMO:CA");
  expect(
    productAuditQuery("SAME", "", parseHash(buildHash("data-assets", source))),
  ).toBeNull();
  expect(
    productAuditQuery("", "DEMO:US", parseHash(buildHash("data-assets", source))),
  ).toBeNull();
});

test.each([
  "#settings",
  "#data-assets?tab=rows",
  "#data-assets?view=rules&tab=impact",
  "#classification-results?tab=impact",
])("拒绝非产品修改记录返回地址：%s", (hash) => {
  expect(productAuditReturnQuery(parseHash(hash))).toBeNull();
});
test("查询只保留现有浏览条件和来源，过滤动作字段及嵌套审计返回", () => {
  const target = productAuditQuery("SAME", "DEMO:US", {
    page: "data-assets",
    query: { ...source, action: "restore", audit_return: "#settings" },
  });
  const original = parseHash(target.audit_return);
  expect(original.query).toEqual(source);
  expect(target.action).toBeUndefined();
});
