import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { useTaskPreflight } from "../src/features/task-create/useTaskPreflight";

const { api } = vi.hoisted(() => ({
  api: { preflightTask: vi.fn(), qualityPreflight: vi.fn() },
}));
vi.mock("../src/api", () => ({ api }));
afterEach(cleanup);
beforeEach(() => vi.resetAllMocks());
const plan = {
  segments: [{ segment_key: "one" }],
  blocked_count: 0,
  plan_hash: "synthetic",
};
const options = {
  configs: [],
  form: {
    dataset_version_id: "synthetic-feedback",
    product_version_id: "synthetic-products",
    config_version_id: "synthetic-config",
  },
  loadingSetup: false,
  prepared: false,
  setSubmitError: vi.fn(),
};

test("创建预检只请求执行计划，不等待或调用额外质量统计", async () => {
  api.preflightTask.mockResolvedValue(plan);
  api.qualityPreflight.mockImplementation(() => {
    throw new Error("额外质量接口不可用");
  });
  const { result } = renderHook(() => useTaskPreflight(options));
  await act(async () => {
    await result.current.runPreflight();
  });
  expect(api.preflightTask).toHaveBeenCalledOnce();
  expect(api.qualityPreflight).not.toHaveBeenCalled();
  expect(result.current.preflight).toEqual({ status: "ready", data: plan, error: "" });
  expect(result.current.segmentSelection.keys).toEqual(["one"]);
});

test("预检失败可重试，重查保留有效选择和顺序", async () => {
  api.preflightTask.mockResolvedValue(plan);
  const { result } = renderHook(() => useTaskPreflight(options));
  await act(async () => {
    await result.current.runPreflight();
  });
  act(() => {
    result.current.segmentSelection.onChange([]);
  });
  api.preflightTask.mockRejectedValueOnce(new Error("合成预检失败"));
  await act(async () => {
    await result.current.runPreflight();
  });
  expect(result.current.preflight.status).toBe("error");
  await act(async () => {
    await result.current.runPreflight();
  });
  expect(result.current.preflight.status).toBe("ready");
  expect(result.current.segmentSelection.keys).toEqual([]);
  expect(result.current.segmentOrder).toEqual(["one"]);
  expect(api.qualityPreflight).not.toHaveBeenCalled();
});

test("更换输入后旧预检响应不能覆盖新范围", async () => {
  let complete;
  api.preflightTask.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        complete = resolve;
      }),
  );
  const { result, rerender } = renderHook((props) => useTaskPreflight(props), {
    initialProps: options,
  });
  let pending;
  act(() => {
    pending = result.current.runPreflight();
  });
  act(() => {
    result.current.invalidatePreflight();
  });
  rerender({
    ...options,
    form: { ...options.form, dataset_version_id: "new-feedback" },
  });
  const next = { ...plan, plan_hash: "new", segments: [{ segment_key: "two" }] };
  api.preflightTask.mockResolvedValue(next);
  await act(async () => {
    await result.current.runPreflight();
  });
  await act(async () => {
    complete(plan);
    await pending;
  });
  expect(result.current.preflight.data).toBe(next);
  expect(result.current.segmentSelection.keys).toEqual(["two"]);
  expect(api.preflightTask.mock.calls[1][0].dataset_version_id).toBe("new-feedback");
});
