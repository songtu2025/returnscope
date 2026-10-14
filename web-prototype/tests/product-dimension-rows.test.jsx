import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithServerState as render } from "./renderWithServerState";

const api = vi.hoisted(() => ({
  datasetRows: vi.fn(),
  updateDatasetRow: vi.fn(),
  dataset: vi.fn(),
}));
vi.mock("../src/api", () => ({ api }));
import { ProductDimensionRows } from "../src/features/data-management/ProductDimensionRows";

const dataset = { id: "synthetic-products", current_version: 2, row_count: 1 };
const row = {
  _row_index: 3,
  MSKU: "SYNTHETIC-SKU",
  "店铺/站点": "SYNTHETIC:US",
  Listing: "SYNTHETIC-LISTING",
};

beforeEach(() => {
  window.location.hash = "#workbench";
  Object.values(api).forEach((mock) => mock.mockReset());
  api.datasetRows.mockResolvedValue({ records: [row], total: 1 });
  api.updateDatasetRow.mockResolvedValue({ ...dataset, current_version: 3 });
  api.dataset.mockResolvedValue({ ...dataset, current_version: 4 });
});

test("产品列表切换页签及返回后恢复路由中的筛选与页码", async () => {
  window.location.hash =
    "#data-assets?rows_q=shoe&rows_store=SYNTHETIC%3AUS&rows_category=footwear&rows_page=2";
  api.datasetRows.mockResolvedValue({
    records: [row],
    total: 45,
    facets: { stores: ["SYNTHETIC:US"], categories: ["footwear"] },
  });
  const user = userEvent.setup();
  const first = render(
    <ProductDimensionRows dataset={dataset} notify={vi.fn()} onChanged={vi.fn()} />,
  );
  await screen.findByText(row.MSKU);
  expect(api.datasetRows).toHaveBeenLastCalledWith(dataset.id, "shoe", 15, 15, {
    store: "SYNTHETIC:US",
    category: "footwear",
  });
  await user.click(screen.getByRole("button", { name: "下一页" }));
  await waitFor(() => expect(window.location.hash).toContain("rows_page=3"));
  first.unmount();
  window.location.hash += "&tab=impact";
  window.location.hash = window.location.hash.replace("tab=impact", "tab=rows");
  render(
    <ProductDimensionRows dataset={dataset} notify={vi.fn()} onChanged={vi.fn()} />,
  );
  await screen.findByText(row.MSKU);
  expect(screen.getByRole("textbox", { name: "搜索产品信息" })).toHaveValue("shoe");
  expect(api.datasetRows).toHaveBeenLastCalledWith(dataset.id, "shoe", 30, 15, {
    store: "SYNTHETIC:US",
    category: "footwear",
  });
});
afterEach(() => cleanup());

async function openEditor(notify = vi.fn(), onChanged = vi.fn()) {
  const user = userEvent.setup();
  render(
    <ProductDimensionRows dataset={dataset} notify={notify} onChanged={onChanged} />,
  );
  await user.click(await screen.findByRole("button", { name: /编辑 .* 产品信息/ }));
  return { user, dialog: screen.getByRole("dialog"), notify, onChanged };
}

test.each([false, true])("行编辑保持可选字段与修改原因原值：%s", async (optional) => {
  const attributes = optional ? { 产品名称: "", 品类A: "鞋履", 品类B: "" } : {};
  api.datasetRows.mockResolvedValue({ records: [{ ...row, ...attributes }], total: 1 });
  const calls = [];
  api.updateDatasetRow.mockImplementation(async () => {
    calls.push("保存");
    return { ...dataset, current_version: 3 };
  });
  const { user, dialog, notify, onChanged } = await openEditor(
    vi.fn(() => calls.push("通知")),
    vi.fn(() => calls.push("版本更新")),
  );
  expect(within(dialog).queryByRole("textbox", { name: "产品名称" }) !== null).toBe(
    optional,
  );
  await user.type(
    within(dialog).getByRole("textbox", { name: "备注（可选）" }),
    " 合成原因 ",
  );
  await user.click(within(dialog).getByRole("button", { name: "保存" }));
  await waitFor(() => expect(onChanged).toHaveBeenCalled());
  expect(api.updateDatasetRow).toHaveBeenCalledWith(dataset.id, {
    row_index: 3,
    expected_version: 2,
    changes: {
      MSKU: row.MSKU,
      "店铺/站点": row["店铺/站点"],
      Listing: row.Listing,
      ...attributes,
    },
    change_note: " 合成原因 ",
  });
  expect(calls).toEqual(["保存", "版本更新", "通知"]);
  expect(notify).toHaveBeenCalledWith("产品信息已更新");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("冲突后核对最新值并保留用户改动及其他人的字段", async () => {
  api.datasetRows.mockResolvedValue({
    records: [{ ...row, 产品名称: "原名称", 品类A: "原品类" }],
    total: 1,
  });
  const { user, dialog, onChanged } = await openEditor();
  await user.clear(within(dialog).getByLabelText("产品名称"));
  await user.type(within(dialog).getByLabelText("产品名称"), "我的名称");
  api.updateDatasetRow.mockRejectedValueOnce(
    Object.assign(new Error("合成冲突"), { status: 409 }),
  );
  await user.click(within(dialog).getByRole("button", { name: "保存", exact: true }));
  expect(await within(dialog).findByRole("alert")).toHaveTextContent("输入已保留");
  api.datasetRows.mockResolvedValue({
    records: [{ ...row, _row_index: 5, 产品名称: "别人名称", 品类A: "别人品类" }],
    total: 1,
  });
  await user.click(within(dialog).getByRole("button", { name: "读取最新资料" }));
  expect(await within(dialog).findByText("别人名称")).toBeVisible();
  expect(within(dialog).getByLabelText("产品名称")).toHaveValue("我的名称");
  expect(
    within(dialog).getByRole("button", { name: "保存", exact: true }),
  ).toBeDisabled();
  await user.click(
    within(dialog).getByRole("button", { name: "已核对，保留我的修改" }),
  );
  expect(within(dialog).getByLabelText("品类A")).toHaveValue("别人品类");
  await user.click(within(dialog).getByRole("button", { name: "保存", exact: true }));
  expect(api.updateDatasetRow).toHaveBeenLastCalledWith(
    dataset.id,
    expect.objectContaining({
      row_index: 5,
      expected_version: 4,
      changes: expect.objectContaining({ 产品名称: "我的名称", 品类A: "别人品类" }),
    }),
  );
  expect(onChanged).toHaveBeenCalledWith(
    expect.objectContaining({ current_version: 3 }),
  );
});

test("读取最新资料失败可重试，产品不存在时不解锁保存", async () => {
  api.updateDatasetRow.mockRejectedValueOnce(
    Object.assign(new Error("冲突"), { status: 409 }),
  );
  const { user, dialog } = await openEditor();
  await user.click(within(dialog).getByRole("button", { name: "保存", exact: true }));
  api.dataset.mockRejectedValueOnce(new Error("读取失败"));
  await user.click(within(dialog).getByRole("button", { name: "读取最新资料" }));
  expect(await within(dialog).findByRole("alert")).toHaveTextContent("读取失败");
  api.datasetRows.mockResolvedValue({ records: [], total: 0 });
  await user.click(within(dialog).getByRole("button", { name: "读取最新资料" }));
  expect(await within(dialog).findByRole("alert")).toHaveTextContent("无法唯一定位");
  expect(
    within(dialog).getByRole("button", { name: "保存", exact: true }),
  ).toBeDisabled();
});

test("未保存输入在取消、关闭和 Escape 时都需要确认", async () => {
  const { user, dialog } = await openEditor();
  await user.type(within(dialog).getByLabelText("备注（可选）"), "我的说明");
  for (const name of ["取消", "关闭"]) {
    await user.click(within(dialog).getByRole("button", { name, exact: true }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("未保存");
    await user.click(within(dialog).getByRole("button", { name: "继续编辑" }));
  }
  await user.keyboard("{Escape}");
  expect(within(dialog).getByRole("alert")).toHaveTextContent("未保存");
  await user.click(within(dialog).getByRole("button", { name: "放弃修改" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("保存中阻止重复提交及取消关闭", async () => {
  let resolveSave;
  api.updateDatasetRow.mockReturnValue(
    new Promise((resolve) => {
      resolveSave = resolve;
    }),
  );
  const { user, dialog, onChanged } = await openEditor();
  await user.type(
    within(dialog).getByRole("textbox", { name: "备注（可选）" }),
    "合成原因",
  );
  await user.click(within(dialog).getByRole("button", { name: "保存" }));
  const saving = within(dialog).getByRole("button", { name: "正在保存…" });
  expect(saving).toBeDisabled();
  await user.click(saving);
  expect(api.updateDatasetRow).toHaveBeenCalledTimes(1);
  await user.click(within(dialog).getByRole("button", { name: "取消" }));
  expect(screen.getByRole("dialog")).toBeVisible();
  await user.click(within(dialog).getByRole("button", { name: "关闭" }));
  await user.keyboard("{Escape}");
  expect(screen.getByRole("dialog")).toBeVisible();
  expect(within(dialog).getByLabelText("备注（可选）")).toBeDisabled();
  await act(async () => resolveSave({ ...dataset, current_version: 3 }));
  expect(onChanged).toHaveBeenCalledWith({ ...dataset, current_version: 3 });
});
