import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { useResultVersionReview } from "../src/features/review-batches/useResultVersionReview";

const mocks = vi.hoisted(() => ({
  classificationResultVersions: vi.fn(),
  reviewBatches: vi.fn(),
  createReviewBatch: vi.fn(),
}));
vi.mock("../src/api", () => ({ api: mocks }));
beforeEach(() => {
  vi.resetAllMocks();
  mocks.classificationResultVersions.mockResolvedValue([]);
  mocks.reviewBatches.mockResolvedValue({ items: [] });
});
afterEach(cleanup);

test.each([
  [new Error("合成加载错误"), "合成加载错误"],
  [{ name: "AbortError", message: "不得采用的对象文案" }, "请求失败"],
  ["合成字符串错误", "请求失败"],
])("加载失败 %# 只读取 Error 实例的文案", async (failure, message) => {
  mocks.classificationResultVersions.mockRejectedValue(failure);
  const { result } = renderHook(() =>
    useResultVersionReview("synthetic-version", vi.fn(), vi.fn()),
  );
  await waitFor(() => expect(result.current.state.error).toBe(message));
  expect(result.current.state.loading).toBe(false);
});

test("Error 实例的 AbortError 保留取消后的加载状态", async () => {
  mocks.classificationResultVersions.mockRejectedValue(
    Object.assign(new Error("合成取消"), { name: "AbortError" }),
  );
  const { result } = renderHook(() =>
    useResultVersionReview("synthetic-version", vi.fn(), vi.fn()),
  );
  await act(async () => {});
  expect(result.current.state).toEqual({
    loading: true,
    error: "",
    history: [],
    batches: [],
  });
});

test.each([
  [{ status: 409, message: "合成对象冲突" }, "请求失败"],
  [new Error(""), ""],
  [new Error("合成创建失败"), "合成创建失败"],
])("创建失败 %# 保留非 Error 与空文案边界", async (failure, message) => {
  mocks.createReviewBatch.mockRejectedValue(failure);
  const notify = vi.fn();
  const openBatch = vi.fn();
  const { result } = renderHook(() =>
    useResultVersionReview("synthetic-version", notify, openBatch),
  );
  await waitFor(() => expect(result.current.state.loading).toBe(false));
  act(() => {
    result.current.setReason(" 合成复核原因 ");
    result.current.setCreateOpen(true);
  });
  await act(async () => result.current.createBatch());
  expect(notify).toHaveBeenCalledWith(message, "error");
  expect(mocks.reviewBatches).toHaveBeenCalledTimes(1);
  expect(openBatch).not.toHaveBeenCalled();
  expect(result.current.reason).toBe(" 合成复核原因 ");
  expect(result.current.createOpen).toBe(true);
  expect(result.current.creating).toBe(false);
  expect(mocks.createReviewBatch).toHaveBeenCalledWith("synthetic-version", {
    reason: "合成复核原因",
  });
});

test("Error 实例的 409 刷新无草稿时保留原冲突反馈", async () => {
  mocks.createReviewBatch.mockRejectedValue(
    Object.assign(new Error("合成冲突"), { status: 409 }),
  );
  const notify = vi.fn();
  const { result } = renderHook(() =>
    useResultVersionReview("synthetic-version", notify, vi.fn()),
  );
  await waitFor(() => expect(result.current.state.loading).toBe(false));
  act(() => result.current.setReason("合成原因"));
  await act(async () => result.current.createBatch());
  expect(mocks.reviewBatches).toHaveBeenCalledTimes(2);
  expect(notify).toHaveBeenCalledWith("合成冲突", "error");
  expect(result.current.creating).toBe(false);
});

test("空白原因不调用创建接口", async () => {
  const { result } = renderHook(() =>
    useResultVersionReview("synthetic-version", vi.fn(), vi.fn()),
  );
  await waitFor(() => expect(result.current.state.loading).toBe(false));
  act(() => result.current.setReason(" \n "));
  await act(async () => result.current.createBatch());
  expect(mocks.createReviewBatch).not.toHaveBeenCalled();
  expect(result.current.creating).toBe(false);
});
