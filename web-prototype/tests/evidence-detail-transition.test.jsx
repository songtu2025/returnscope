import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SWRConfig } from "swr";
import { useClassificationResultDetailData } from "../src/features/classification-results/useClassificationResultDetailData";

const reads = vi.hoisted(() => ({ overview: vi.fn(), records: vi.fn() }));
vi.mock("../src/features/classification-results/classificationResultReads", () => ({
  readResultOverview: reads.overview,
  readResultRecords: reads.records,
  resultRecordQuery: () => ({ page: 1, page_size: 20 }),
}));
afterEach(cleanup);

test("保存后切换结果的慢读取保留详情，关闭复核后显示最新结果", async () => {
  let resolveNext;
  let resolveRecords;
  reads.records.mockImplementation((version) =>
    version === "v1"
      ? Promise.resolve({ records: { items: [], total: 2 }, drilldowns: {} })
      : new Promise((resolve) => {
          resolveRecords = resolve;
        }),
  );
  reads.overview.mockImplementation((version) =>
    version === "v1"
      ? Promise.resolve({ result: { version_id: "v1" }, summary: {} })
      : new Promise((resolve) => {
          resolveNext = resolve;
        }),
  );
  const cache = new Map();
  const view = renderHook(
    ({ version, protectedOperation }) =>
      useClassificationResultDetailData({
        route: { version, tab: "records" },
        notify: vi.fn(),
        protectedOperation,
      }),
    {
      initialProps: { version: "v1", protectedOperation: false },
      wrapper: ({ children }) => (
        <SWRConfig value={{ provider: () => cache }}>{children}</SWRConfig>
      ),
    },
  );
  await waitFor(() => expect(view.result.current.result?.version_id).toBe("v1"));
  await waitFor(() => expect(view.result.current.records?.total).toBe(2));
  view.rerender({ version: "v1", protectedOperation: true });
  view.rerender({ version: "v2", protectedOperation: true });
  expect(view.result.current.result?.version_id).toBe("v1");
  expect(view.result.current.records?.total).toBe(2);
  await waitFor(() => expect(resolveNext).toBeTypeOf("function"));
  await waitFor(() => expect(resolveRecords).toBeTypeOf("function"));
  await act(async () => {
    resolveNext({ result: { version_id: "v2" }, summary: {} });
    resolveRecords({ records: { items: [], total: 1 }, drilldowns: {} });
  });
  expect(view.result.current.result).not.toBeNull();
  view.rerender({ version: "v2", protectedOperation: false });
  await waitFor(() => expect(view.result.current.result?.version_id).toBe("v2"));
  expect(view.result.current.records?.total).toBe(1);
});
