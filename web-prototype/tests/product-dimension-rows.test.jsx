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
  Object.values(api).forEach((mock) => mock.mockReset());
  api.datasetRows.mockResolvedValue({ records: [row], total: 1 });
  api.updateDatasetRow.mockResolvedValue({ ...dataset, current_version: 3 });
  api.dataset.mockResolvedValue({ ...dataset, current_version: 4 });
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
    within(dialog).getByRole("textbox", { name: "修改原因" }),
    " 合成原因 ",
  );
  await user.click(within(dialog).getByRole("button", { name: "保存并创建新版本" }));
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
  expect(notify).toHaveBeenCalledWith("产品信息已更新，并创建了新版本");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test.each([true, false])("仅Error对象的409刷新版本：%s", async (errorObject) => {
  const error = errorObject
    ? Object.assign(new Error("合成冲突"), { status: 409 })
    : { status: 409, message: "合成对象错误" };
  api.updateDatasetRow.mockRejectedValue(error);
  const calls = [];
  api.dataset.mockImplementation(async () => {
    calls.push("读取版本");
    return { ...dataset, current_version: 4 };
  });
  const { user, dialog, notify, onChanged } = await openEditor(
    vi.fn(() => calls.push("通知")),
    vi.fn(() => calls.push("版本更新")),
  );
  await user.type(
    within(dialog).getByRole("textbox", { name: "修改原因" }),
    "合成原因",
  );
  await user.click(within(dialog).getByRole("button", { name: "保存并创建新版本" }));
  await waitFor(() => expect(notify).toHaveBeenCalled());
  if (errorObject) {
    expect(api.dataset).toHaveBeenCalledWith(dataset.id, { include: "versions" });
    expect(onChanged).toHaveBeenCalledWith({ ...dataset, current_version: 4 });
    expect(calls).toEqual(["读取版本", "版本更新", "通知"]);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(notify).toHaveBeenCalledWith(
      "数据已被其他用户更新，已刷新到最新版本，请重新修改",
      "error",
    );
  } else {
    expect(api.dataset).not.toHaveBeenCalled();
    expect(onChanged).not.toHaveBeenCalled();
    expect(notify).toHaveBeenCalledWith("请求失败", "error");
    expect(within(dialog).getByRole("textbox", { name: "修改原因" })).toHaveValue(
      "合成原因",
    );
    expect(
      within(dialog).getByRole("button", { name: "保存并创建新版本" }),
    ).toBeEnabled();
  }
});

test("保存中阻止重复提交并保留原取消行为", async () => {
  let resolveSave;
  api.updateDatasetRow.mockReturnValue(
    new Promise((resolve) => {
      resolveSave = resolve;
    }),
  );
  const { user, dialog, onChanged } = await openEditor();
  await user.type(
    within(dialog).getByRole("textbox", { name: "修改原因" }),
    "合成原因",
  );
  await user.click(within(dialog).getByRole("button", { name: "保存并创建新版本" }));
  const saving = within(dialog).getByRole("button", { name: "正在创建新版本…" });
  expect(saving).toBeDisabled();
  await user.click(saving);
  expect(api.updateDatasetRow).toHaveBeenCalledTimes(1);
  await user.click(within(dialog).getByRole("button", { name: "取消" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await act(async () => resolveSave({ ...dataset, current_version: 3 }));
  expect(onChanged).toHaveBeenCalledWith({ ...dataset, current_version: 3 });
});
