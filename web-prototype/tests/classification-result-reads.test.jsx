import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { SWRConfig } from "swr";
import { classificationResultRouteState } from "../src/features/classification-results/classificationResultRoute";

const { apiMock, readsMock } = vi.hoisted(() => ({
  apiMock: { classificationResults: vi.fn(), classificationResultVersions: vi.fn() },
  readsMock: { readResultOverview: vi.fn(), readResultRecords: vi.fn() },
}));
vi.mock("../src/api", () => ({ api: apiMock }));
vi.mock(
  "../src/features/classification-results/classificationResultReads",
  async (load) => ({
    ...(await load()),
    ...readsMock,
  }),
);

import { useClassificationResultListData } from "../src/features/classification-results/useClassificationResultListData";
import { useClassificationResultOverview } from "../src/features/classification-results/useClassificationResultOverview";
import { useClassificationResultRecords } from "../src/features/classification-results/useClassificationResultRecords";
import { useLatestResult } from "../src/features/classification-results/useLatestResult";

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

function wrapper({ children }) {
  return (
    <SWRConfig value={{ provider: () => new Map(), shouldRetryOnError: false }}>
      {children}
    </SWRConfig>
  );
}

const route = (query) => classificationResultRouteState(query);
const cases = [
  {
    name: "结果池筛选",
    mock: apiMock.classificationResults,
    useRead: (q) => useClassificationResultListData({ q }),
    value: (q) => ({ items: [{ version_id: q }], total: 1 }),
    displayed: (state) => state.data?.items[0].version_id,
  },
  {
    name: "结果概况版本切换",
    mock: readsMock.readResultOverview,
    useRead: (version) => useClassificationResultOverview(version),
    value: (version) => ({ result: { version_id: version }, summary: {} }),
    displayed: (state) => state.result?.version_id,
  },
  {
    name: "反馈明细查询",
    mock: readsMock.readResultRecords,
    useRead: (orderId) =>
      useClassificationResultRecords({
        route: route({ result_version_id: "result", order_id: orderId }),
        notify: vi.fn(),
      }),
    value: (orderId) => ({ records: { items: [{ orderId }] }, drilldowns: {} }),
    displayed: (state) => state.records?.items[0].orderId,
  },
  {
    name: "最新结果版本读取",
    mock: apiMock.classificationResultVersions,
    useRead: (version) =>
      useLatestResult({
        route: route({ result_version_id: version }),
        result: { version_id: version, version: 1 },
        protectedOperation: true,
        updateRoute: vi.fn(),
        refreshAttempt: 0,
      }),
    value: () => [],
    displayed: () => undefined,
  },
];

function delayedReads(mock) {
  const requests = [];
  mock.mockImplementation(
    (...args) =>
      new Promise((resolve, reject) => {
        const { signal } = args.at(-1);
        requests.push({ signal, resolve, reject });
        signal.addEventListener(
          "abort",
          () => reject(new DOMException("取消旧读取", "AbortError")),
          { once: true },
        );
      }),
  );
  return requests;
}

test.each(cases)("$name：旧查询清理不能取消新查询，完成后显示新数据", async (entry) => {
  const requests = delayedReads(entry.mock);
  const view = renderHook(({ identity }) => entry.useRead(identity), {
    wrapper,
    initialProps: { identity: "first" },
  });
  await waitFor(() => expect(requests).toHaveLength(1));
  await act(async () => requests[0].resolve(entry.value("first")));
  view.rerender({ identity: "second" });
  await waitFor(() => expect(requests).toHaveLength(2));
  expect(requests[1].signal.aborted).toBe(false);
  await act(async () => requests[1].resolve(entry.value("second")));
  if (entry.name !== "最新结果版本读取") {
    await waitFor(() => expect(entry.displayed(view.result.current)).toBe("second"));
  }
});

test.each(cases)("$name：快速切换取消旧读取，卸载仅取消当前读取", async (entry) => {
  const requests = delayedReads(entry.mock);
  const view = renderHook(({ identity }) => entry.useRead(identity), {
    wrapper,
    initialProps: { identity: "first" },
  });
  await waitFor(() => expect(requests).toHaveLength(1));
  view.rerender({ identity: "second" });
  await waitFor(() => expect(requests).toHaveLength(2));
  expect(requests[0].signal.aborted).toBe(true);
  expect(requests[1].signal.aborted).toBe(false);
  await act(async () => requests[0].resolve(entry.value("first")));
  expect(entry.displayed(view.result.current)).not.toBe("first");
  view.unmount();
  expect(requests[1].signal.aborted).toBe(true);
});

test.each(cases)("$name：切换后的读取失败提供错误信息", async (entry) => {
  const requests = delayedReads(entry.mock);
  const view = renderHook(({ identity }) => entry.useRead(identity), {
    wrapper,
    initialProps: { identity: "first" },
  });
  await waitFor(() => expect(requests).toHaveLength(1));
  await act(async () => requests[0].resolve(entry.value("first")));
  view.rerender({ identity: "second" });
  await waitFor(() => expect(requests).toHaveLength(2));
  await act(async () => requests[1].reject(new Error("合成读取失败")));
  await waitFor(() => {
    const state = view.result.current;
    expect(typeof state === "string" ? state : state.error || state.recordsError).toBe(
      "合成读取失败",
    );
  });
});

test("看板来源固定在所选结果版本，不自动切换最新版", () => {
  const updateRoute = vi.fn();
  renderHook(
    () =>
      useLatestResult({
        route: route({
          result_version_id: "source-v1",
          dashboard_return: "#analysis-dashboards?dashboard=demo",
        }),
        result: { version_id: "source-v1", version: 1 },
        protectedOperation: false,
        updateRoute,
        refreshAttempt: 0,
      }),
    { wrapper },
  );
  expect(apiMock.classificationResultVersions).not.toHaveBeenCalled();
  expect(updateRoute).not.toHaveBeenCalled();
});
