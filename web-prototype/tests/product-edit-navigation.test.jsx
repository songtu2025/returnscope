import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { useProductRowEditing } from "../src/features/data-management/useProductRowEditing";
import { ProductDimensionEditDialog } from "../src/features/data-management/ProductDimensionEditDialog";
import { requestNavigation } from "../src/app/navigationGuard";
const api = vi.hoisted(() => ({
  updateDatasetRow: vi.fn(),
  dataset: vi.fn(),
  datasetRows: vi.fn(),
}));
vi.mock("../src/api", () => ({ api }));
const row = {
  _row_index: 1,
  MSKU: "SKU",
  Listing: "LIST",
  "店铺/站点": "TEST:US",
  产品名称: "原名",
};
const nextRow = { ...row, _row_index: 2, MSKU: "NEXT", 产品名称: "下一商品" };
function Harness({ pageRows = [row], notify = vi.fn() }) {
  const edit = useProductRowEditing({
    dataset: { id: "data", current_version: 1 },
    notify,
    onChanged: vi.fn(),
  });
  return (
    <>
      <button onClick={() => edit.open(pageRows[0], pageRows)}>编辑</button>
      {edit.editing && (
        <ProductDimensionEditDialog
          {...edit}
          editing={edit.editing}
          onSave={edit.save}
          onClose={edit.close}
        />
      )}
    </>
  );
}
beforeEach(() => {
  api.updateDatasetRow.mockReset();
  api.dataset.mockReset().mockResolvedValue({ id: "data", current_version: 7 });
  api.datasetRows.mockReset().mockResolvedValue({
    records: [{ ...nextRow, _row_index: 80, 产品名称: "下一商品最新名称" }],
  });
  api.updateDatasetRow.mockResolvedValue({ id: "data", current_version: 2 });
});
afterEach(cleanup);
function editProduct() {
  render(<Harness />);
  fireEvent.click(screen.getByRole("button", { name: "编辑", exact: true }));
  fireEvent.change(screen.getByLabelText("产品名称"), { target: { value: "新名" } });
}
test("产品普通保存期间导航，保存成功卸载编辑器仍执行目标且不重复保存", async () => {
  let finish;
  api.updateDatasetRow.mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  editProduct();
  const proceed = vi.fn();
  fireEvent.submit(screen.getByLabelText("产品名称").closest("form"));
  act(() => requestNavigation(proceed));
  expect(proceed).not.toHaveBeenCalled();
  await act(async () => finish({ id: "data", current_version: 2 }));
  await waitFor(() => expect(proceed).toHaveBeenCalledOnce());
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(api.updateDatasetRow).toHaveBeenCalledOnce();
});
test("产品退出保存完成即使编辑器卸载仍执行目标导航", async () => {
  editProduct();
  const proceed = vi.fn();
  act(() => requestNavigation(proceed));
  fireEvent.click(screen.getByRole("button", { name: "保存后离开" }));
  await waitFor(() => expect(proceed).toHaveBeenCalledOnce());
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(api.updateDatasetRow).toHaveBeenCalledOnce();
});
test("产品关闭路由确认保留字段且不弹内部确认，改回原值不拦", () => {
  editProduct();
  act(() => requestNavigation(vi.fn()));
  expect(screen.getAllByRole("dialog")).toHaveLength(1);
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByText(/有未保存的修改/)).not.toBeInTheDocument();
  expect(screen.getByLabelText("产品名称")).toHaveValue("新名");
  fireEvent.change(screen.getByLabelText("产品名称"), { target: { value: "原名" } });
  expect(requestNavigation(vi.fn())).toBe(true);
});
test("产品必填校验和冲突都阻止保存退出，草稿保留", async () => {
  editProduct();
  const proceed = vi.fn();
  fireEvent.change(screen.getByLabelText("MSKU"), { target: { value: "" } });
  act(() => requestNavigation(proceed));
  fireEvent.click(screen.getByRole("button", { name: "保存后离开" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "保存后离开" })).toBeEnabled(),
  );
  expect(api.updateDatasetRow).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("MSKU"), { target: { value: "SKU" } });
  api.updateDatasetRow.mockRejectedValueOnce(
    Object.assign(new Error("冲突"), { status: 409 }),
  );
  fireEvent.click(screen.getByRole("button", { name: "保存后离开" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "保存后离开" })).toBeDisabled(),
  );
  expect(screen.getByLabelText("产品名称")).toHaveValue("新名");
  expect(proceed).not.toHaveBeenCalled();
});

function editWithNext(notify) {
  render(<Harness pageRows={[row, nextRow]} notify={notify} />);
  fireEvent.click(screen.getByRole("button", { name: "编辑", exact: true }));
  fireEvent.change(screen.getByLabelText("产品名称"), {
    target: { value: "本条新名" },
  });
  fireEvent.change(screen.getByLabelText("备注（可选）"), {
    target: { value: "仅本条备注" },
  });
}

test("逐条保存沿当前页顺序读取最新行索引和版本，不沿用上条输入、备注或其他店铺", async () => {
  api.datasetRows.mockResolvedValueOnce({
    records: [
      { ...nextRow, "店铺/站点": "OTHER:US" },
      { ...nextRow, _row_index: 80, 产品名称: "下一商品最新名称" },
    ],
  });
  editWithNext();
  fireEvent.change(screen.getByLabelText("MSKU"), {
    target: { value: "FIRST-RENAMED" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存并编辑下一条" }));
  await waitFor(() => expect(screen.getByLabelText("MSKU")).toHaveValue("NEXT"));
  expect(screen.getByLabelText("产品名称")).toHaveValue("下一商品最新名称");
  expect(screen.getByLabelText("备注（可选）")).toHaveValue("");
  expect(api.datasetRows).toHaveBeenCalledWith("data", "NEXT", 0, 100, {
    store: "TEST:US",
    version: 7,
  });
  expect(api.updateDatasetRow).toHaveBeenCalledOnce();
  expect(api.updateDatasetRow.mock.calls[0][1]).toMatchObject({
    row_index: 1,
    expected_version: 1,
    change_note: "仅本条备注",
    changes: { MSKU: "FIRST-RENAMED", 产品名称: "本条新名" },
  });
  expect(screen.getByRole("button", { name: "保存并编辑下一条" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "保存", exact: true }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(api.updateDatasetRow.mock.calls[1][1]).toMatchObject({
    row_index: 80,
    expected_version: 7,
    change_note: "",
    changes: { MSKU: "NEXT", 产品名称: "下一商品最新名称" },
  });
});

test.each([400, 409, 500])(
  "保存失败 %s 保留当前条输入，不读取或跳转下一条",
  async (status) => {
    api.updateDatasetRow.mockRejectedValueOnce(
      Object.assign(new Error("合成失败"), { status }),
    );
    editWithNext();
    fireEvent.click(screen.getByRole("button", { name: "保存并编辑下一条" }));
    await screen.findByRole("alert");
    expect(screen.getByLabelText("MSKU")).toHaveValue("SKU");
    expect(screen.getByLabelText("产品名称")).toHaveValue("本条新名");
    expect(screen.getByLabelText("备注（可选）")).toHaveValue("仅本条备注");
    expect(api.datasetRows).not.toHaveBeenCalled();
    if (status === 409)
      expect(screen.getByRole("button", { name: "保存并编辑下一条" })).toBeDisabled();
  },
);

test("下一条同样执行必填校验，保存和读取期间禁止重复提交", async () => {
  editWithNext();
  fireEvent.change(screen.getByLabelText("MSKU"), { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "保存并编辑下一条" }));
  expect(api.updateDatasetRow).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("MSKU"), { target: { value: "SKU" } });
  let finish;
  api.datasetRows.mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: "保存并编辑下一条" }));
  await waitFor(() => expect(api.datasetRows).toHaveBeenCalledOnce());
  fireEvent.click(screen.getByRole("button", { name: "保存并编辑下一条" }));
  expect(api.updateDatasetRow).toHaveBeenCalledOnce();
  await act(async () => finish({ records: [nextRow] }));
  expect(screen.getByLabelText("MSKU")).toHaveValue("NEXT");
});

test.each([[], [nextRow, nextRow]])(
  "保存已成功但下一条不能唯一定位时不重复保存：%j",
  async (records) => {
    const notify = vi.fn();
    api.datasetRows.mockResolvedValueOnce({ records });
    editWithNext(notify);
    fireEvent.click(screen.getByRole("button", { name: "保存并编辑下一条" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(notify).toHaveBeenCalledWith(
      expect.stringContaining("当前产品已保存，下一条读取失败"),
      "error",
    );
    expect(api.updateDatasetRow).toHaveBeenCalledOnce();
  },
);
