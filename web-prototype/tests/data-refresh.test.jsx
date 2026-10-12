import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { useDataRefresh } from "../src/hooks/useDataRefresh";
import { notifyDataChanged } from "../src/shared/refreshPolicy";
import { refreshServerState } from "../src/shared/serverState";

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});
const advance = async (time) => act(async () => vi.advanceTimersByTimeAsync(time));

test("焦点、联网和可见性恢复合并，使用最新刷新回调，卸载后停止", async () => {
  const first = vi.fn().mockResolvedValue(null);
  const second = vi.fn().mockResolvedValue(null);
  const view = renderHook(({ refresh }) => useDataRefresh(refresh), {
    initialProps: { refresh: first },
  });
  view.rerender({ refresh: second });
  act(() => {
    window.dispatchEvent(new Event("focus"));
    window.dispatchEvent(new Event("online"));
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await advance(100);
  expect(first).not.toHaveBeenCalled();
  expect(second).toHaveBeenCalledOnce();
  act(() => window.dispatchEvent(new Event("focus")));
  await advance(100);
  expect(second).toHaveBeenCalledOnce();
  await advance(60000);
  expect(second).toHaveBeenCalledTimes(2);
  view.unmount();
  act(() => window.dispatchEvent(new Event("focus")));
  await advance(60000);
  expect(second).toHaveBeenCalledTimes(2);
});

test("隐藏或离线不轮询，恢复后只读取一次", async () => {
  const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(true);
  const online = vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
  const refresh = vi.fn().mockResolvedValue(null);
  renderHook(() => useDataRefresh(refresh, { interval: 2000 }));
  await advance(5000);
  expect(refresh).not.toHaveBeenCalled();
  hidden.mockReturnValue(false);
  online.mockReturnValue(false);
  await advance(3000);
  expect(refresh).not.toHaveBeenCalled();
  online.mockReturnValue(true);
  act(() => {
    window.dispatchEvent(new Event("online"));
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await advance(100);
  expect(refresh).toHaveBeenCalledOnce();
});

test("慢请求不重叠，读取中发生保存变更会在完成后再同步一次", async () => {
  let resolve;
  const refresh = vi
    .fn()
    .mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    )
    .mockResolvedValue(null);
  renderHook(() => useDataRefresh(refresh, { interval: 2000, domains: ["results"] }));
  await advance(2100);
  await advance(5000);
  expect(refresh).toHaveBeenCalledOnce();
  act(() => {
    notifyDataChanged(["products"]);
    notifyDataChanged(["results"]);
    notifyDataChanged(["results"]);
  });
  await act(async () => resolve());
  await advance(250);
  expect(refresh).toHaveBeenCalledTimes(2);
});

test("前景读取时不重复触发，待处理的保存变更在前景读取完成后恢复", async () => {
  const refresh = vi.fn().mockResolvedValue(null);
  const view = renderHook(
    ({ loading }) => useDataRefresh(refresh, { loading, domains: ["results"] }),
    { initialProps: { loading: true } },
  );
  act(() => {
    window.dispatchEvent(new Event("focus"));
    notifyDataChanged(["results"]);
  });
  await advance(100);
  expect(refresh).not.toHaveBeenCalled();
  view.rerender({ loading: false });
  await advance(250);
  expect(refresh).toHaveBeenCalledOnce();
});

test("临时读取失败后下一周期继续恢复，任务结束后不再轮询", async () => {
  const refresh = vi
    .fn()
    .mockRejectedValueOnce(new Error("合成读取失败"))
    .mockResolvedValue(null);
  const view = renderHook(
    ({ enabled }) => useDataRefresh(refresh, { enabled, interval: 2000 }),
    { initialProps: { enabled: true } },
  );
  await advance(2100);
  expect(refresh).toHaveBeenCalledOnce();
  await advance(2000);
  expect(refresh).toHaveBeenCalledTimes(2);
  view.rerender({ enabled: false });
  await advance(10000);
  expect(refresh).toHaveBeenCalledTimes(2);
});

test("保存只刷新关联缓存，保留原缓存值并通知非 SWR 模块", () => {
  const listener = vi.fn();
  window.addEventListener("seekway:data-changed", listener);
  const mutate = vi.fn().mockResolvedValue([]);
  refreshServerState(mutate, ["classification-results", "analysis-dashboards"]);
  expect(mutate).toHaveBeenCalledOnce();
  const [predicate, ...rest] = mutate.mock.calls[0];
  expect(rest).toEqual([]);
  expect(predicate(["classification-results", "records", "synthetic"])).toBe(true);
  expect(predicate(["analysis-dashboards", "list"])).toBe(true);
  expect(predicate(["task-create", "setup"])).toBe(false);
  expect(listener.mock.calls[0][0].detail).toEqual([
    "classification-results",
    "analysis-dashboards",
  ]);
  window.removeEventListener("seekway:data-changed", listener);
});
