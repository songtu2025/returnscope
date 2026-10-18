import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { useSegmentBoardView } from "../src/features/task-runtime/useSegmentBoardView";

afterEach(cleanup);
const segments = Array.from({ length: 25 }, (_, index) => ({
  id: `segment-${index}`,
  segment_key: `key-${index}`,
}));
const snapshot = {
  taskId: "task-1",
  segmentId: "segment-24",
  query: "保留查询",
  statusFilter: "attention",
  page: 2,
  expandedSegmentKey: "key-24",
};
const options = {
  taskId: "task-1",
  segments,
  pageSize: 20,
  focusSegmentId: "segment-24",
  initialFilter: "all",
};

test.each([{ taskId: "other-task" }, { focusSegmentId: "segment-23" }])(
  "外部定位不使用其他任务或其他目标的返回状态 %s",
  async (changes) => {
    const returnState = { current: { ...snapshot } };
    const { result } = renderHook(() =>
      useSegmentBoardView({ ...options, ...changes, returnState }),
    );
    await waitFor(() => expect(result.current.page).toBe(2));
    expect(result.current.query).toBe("");
    expect(result.current.statusFilter).toBe("all");
    expect(result.current.expandedSegmentKey).toBeNull();
  },
);

test("恢复第二页后继续改变筛选仍回第一页", async () => {
  const returnState = { current: { ...snapshot } };
  const { result } = renderHook(() => useSegmentBoardView({ ...options, returnState }));
  expect(result.current.page).toBe(2);
  expect(result.current.expandedSegmentKey).toBe("key-24");
  act(() => result.current.setQuery("新查询"));
  await waitFor(() => expect(result.current.page).toBe(1));
  act(() => result.current.setPage(2));
  act(() => result.current.setStatusFilter("delivered"));
  expect(result.current.page).toBe(1);
});
