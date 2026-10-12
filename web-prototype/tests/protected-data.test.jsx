import { cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { useProtectedData } from "../src/hooks/useProtectedData";

afterEach(cleanup);

test("编辑时保留当前展示，后台完成更新后在结束操作时一起应用", () => {
  const before = { records: ["旧记录"], summary: { ready: 1 } };
  const after = { records: ["新记录"], summary: { ready: 2 } };
  const view = renderHook(
    ({ value, protectedOperation }) =>
      useProtectedData(value, protectedOperation, "same-query"),
    { initialProps: { value: before, protectedOperation: false } },
  );
  view.rerender({ value: after, protectedOperation: true });
  expect(view.result.current).toBe(before);
  view.rerender({ value: after, protectedOperation: false });
  expect(view.result.current).toBe(after);
});

test("跨页勾选时显式改变查询仍读取新页，首次数据不会被保护成空白", () => {
  const first = { records: ["第一页"] };
  const second = { records: ["第二页"] };
  const view = renderHook(({ value, key }) => useProtectedData(value, true, key), {
    initialProps: { value: first, key: "page-1" },
  });
  view.rerender({ value: undefined, key: "page-2" });
  expect(view.result.current).toBeUndefined();
  view.rerender({ value: second, key: "page-2" });
  expect(view.result.current).toBe(second);
  view.rerender({ value: { records: ["后台替换"] }, key: "page-2" });
  expect(view.result.current).toBe(second);
});
