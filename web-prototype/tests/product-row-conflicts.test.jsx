import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { useProductRowEditing } from "../src/features/data-management/useProductRowEditing";

const api = vi.hoisted(() => ({
  dataset: vi.fn(),
  datasetRows: vi.fn(),
  updateDatasetRow: vi.fn(),
}));
vi.mock("../src/api", () => ({ api }));
const row = {
  _row_index: 1,
  MSKU: "TEST-SKU",
  "店铺/站点": "TEST:US",
  Listing: "TEST",
  产品名称: "原名",
  品类A: "原品类",
};
const dataset = { id: "test-data", current_version: 1 };
const event = { preventDefault: vi.fn() };
beforeEach(() => {
  Object.values(api).forEach((mock) => mock.mockReset());
  api.dataset.mockResolvedValue({ ...dataset, current_version: 2 });
  api.updateDatasetRow
    .mockRejectedValueOnce(Object.assign(new Error("冲突"), { status: 409 }))
    .mockResolvedValue({ ...dataset, current_version: 3 });
});
afterEach(cleanup);

async function conflictWith(mine, latest) {
  const props = { dataset, notify: vi.fn(), onChanged: vi.fn() };
  const { result } = renderHook(() => useProductRowEditing(props));
  act(() => result.current.open(row));
  act(() => result.current.setEditing({ ...row, ...mine }));
  await act(() => result.current.save(event));
  api.datasetRows.mockResolvedValue({
    records: [{ ...row, _row_index: 5, ...latest }],
  });
  await act(() => result.current.loadLatest());
  return { result, props };
}

test("不同字段修改自动合并并使用最新行号与版本保存", async () => {
  const { result } = await conflictWith(
    { 产品名称: "我的名称" },
    { 品类A: "最新品类" },
  );
  expect(result.current.conflictFields).toEqual([]);
  act(() => result.current.acceptLatest());
  expect(result.current.editing).toMatchObject({
    产品名称: "我的名称",
    品类A: "最新品类",
  });
  await act(() => result.current.save(event));
  expect(api.updateDatasetRow).toHaveBeenLastCalledWith(
    dataset.id,
    expect.objectContaining({
      row_index: 5,
      expected_version: 2,
      changes: expect.objectContaining({ 产品名称: "我的名称", 品类A: "最新品类" }),
    }),
  );
});

test("同字段改成相同最终值无需选择", async () => {
  const { result } = await conflictWith(
    { 产品名称: "共同名称" },
    { 产品名称: "共同名称" },
  );
  expect(result.current.unresolved).toEqual([]);
  act(() => result.current.acceptLatest());
  expect(result.current.conflict).toBe(false);
  expect(result.current.editing.产品名称).toBe("共同名称");
});

test("双方不同值必须逐字段选择，未选全不能应用或保存", async () => {
  const { result } = await conflictWith(
    { 产品名称: "我的名称", 品类A: "我的品类" },
    { 产品名称: "最新名称", 品类A: "最新品类" },
  );
  expect(result.current.unresolved).toEqual(["产品名称", "品类A"]);
  act(() => result.current.resolveField("产品名称", "mine"));
  act(() => result.current.acceptLatest());
  await act(() => result.current.save(event));
  expect(api.updateDatasetRow).toHaveBeenCalledTimes(1);
  expect(result.current.conflict).toBe(true);
  act(() => result.current.resolveField("品类A", "latest"));
  act(() => result.current.acceptLatest());
  await act(() => result.current.save(event));
  expect(api.updateDatasetRow).toHaveBeenLastCalledWith(
    dataset.id,
    expect.objectContaining({
      expected_version: 2,
      changes: expect.objectContaining({ 产品名称: "我的名称", 品类A: "最新品类" }),
    }),
  );
});

test("再次编辑冲突字段使旧选择失效，改成最新值后可自动解除", async () => {
  const { result } = await conflictWith(
    { 产品名称: "我的名称" },
    { 产品名称: "最新名称" },
  );
  act(() => result.current.resolveField("产品名称", "mine"));
  act(() =>
    result.current.setEditing({ ...result.current.editing, 产品名称: "再次修改" }),
  );
  expect(result.current.unresolved).toEqual(["产品名称"]);
  act(() => result.current.acceptLatest());
  expect(result.current.conflict).toBe(true);
  act(() =>
    result.current.setEditing({ ...result.current.editing, 产品名称: "最新名称" }),
  );
  expect(result.current.unresolved).toEqual([]);
  act(() => result.current.acceptLatest());
  expect(result.current.conflict).toBe(false);
});

test("再次409仍使用更新的基准比较，保留草稿并重新选择", async () => {
  const { result } = await conflictWith(
    { 产品名称: "我的名称" },
    { 产品名称: "第二版名称" },
  );
  act(() => result.current.resolveField("产品名称", "mine"));
  act(() => result.current.acceptLatest());
  api.updateDatasetRow.mockRejectedValueOnce(
    Object.assign(new Error("再次冲突"), { status: 409 }),
  );
  await act(() => result.current.save(event));
  expect(result.current.editing.产品名称).toBe("我的名称");
  expect(result.current.latest).toBeNull();
  api.dataset.mockResolvedValue({ ...dataset, current_version: 4 });
  api.datasetRows.mockResolvedValue({ records: [{ ...row, 产品名称: "第四版名称" }] });
  await act(() => result.current.loadLatest());
  expect(result.current.original.产品名称).toBe("第二版名称");
  expect(result.current.unresolved).toEqual(["产品名称"]);
  act(() => result.current.resolveField("产品名称", "latest"));
  act(() => result.current.acceptLatest());
  await act(() => result.current.save(event));
  expect(api.updateDatasetRow).toHaveBeenLastCalledWith(
    dataset.id,
    expect.objectContaining({
      expected_version: 4,
      changes: expect.objectContaining({ 产品名称: "第四版名称" }),
    }),
  );
});

test("读取失败保留输入并可重试，核对期间关闭仍保护草稿", async () => {
  const { result } = await conflictWith(
    { 产品名称: "我的名称" },
    { 产品名称: "最新名称" },
  );
  api.dataset.mockRejectedValueOnce(new Error("读取失败"));
  await act(() => result.current.loadLatest());
  expect(result.current.error).toBe("读取失败");
  expect(result.current.editing.产品名称).toBe("我的名称");
  expect(result.current.conflict).toBe(true);
  act(() => result.current.close());
  expect(result.current.confirmClose).toBe(true);
  act(() => result.current.continueEditing());
  expect(result.current.editing.产品名称).toBe("我的名称");
  await act(() => result.current.loadLatest());
  expect(result.current.error).toBe("");
  expect(result.current.unresolved).toEqual(["产品名称"]);
});
