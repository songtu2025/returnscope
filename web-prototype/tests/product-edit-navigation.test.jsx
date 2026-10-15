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
const api = vi.hoisted(() => ({ updateDatasetRow: vi.fn() }));
vi.mock("../src/api", () => ({ api }));
const row = {
  _row_index: 1,
  MSKU: "SKU",
  Listing: "LIST",
  "店铺/站点": "TEST:US",
  产品名称: "原名",
};
function Harness() {
  const edit = useProductRowEditing({
    dataset: { id: "data", current_version: 1 },
    notify: vi.fn(),
    onChanged: vi.fn(),
  });
  return (
    <>
      <button onClick={() => edit.open(row)}>编辑</button>
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
