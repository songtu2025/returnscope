import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    activeValidation: vi.fn(),
    validationEventUrl: vi.fn(),
    validationRun: vi.fn(),
  },
}));

vi.mock("../src/shared/api/modelApi", () => ({ modelApi: apiMock }));

import { useModelValidationRun } from "../src/features/system-settings/useModelValidationRun";

const originalEventSource = globalThis.EventSource;
/** @type {EventSourceProbe[]} */
let sources = [];

class EventSourceProbe {
  constructor(url, options) {
    this.url = url;
    this.options = options;
    this.closed = false;
    this.listeners = new Map();
    sources.push(this);
  }

  addEventListener(type, listener) {
    this.listeners.set(type, listener);
  }

  emit(type, value = {}) {
    this.listeners.get(type)?.({ data: JSON.stringify(value) });
  }

  close() {
    this.closed = true;
  }
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function run(id, status = "running") {
  return {
    id,
    status,
    created_at: "2026-09-28T00:00:00Z",
    started_at: "2026-09-28T00:00:00Z",
  };
}

const notify = vi.fn();
const onCompleted = vi.fn();

function renderValidation(connectionId = "connection-a") {
  return renderHook(
    ({ connectionId: selectedId }) =>
      useModelValidationRun({
        connectionId: selectedId,
        notify,
        onCompleted,
      }),
    { initialProps: { connectionId } },
  );
}

beforeEach(() => {
  sources = [];
  globalThis.EventSource = EventSourceProbe;
  Object.values(apiMock).forEach((mock) => mock.mockReset());
  apiMock.activeValidation.mockResolvedValue(null);
  apiMock.validationEventUrl.mockImplementation((id) => `/validation/${id}`);
  notify.mockReset();
  onCompleted.mockReset().mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
  globalThis.EventSource = originalEventSource;
});

test("切换连接后忽略旧连接的活动验证结果", async () => {
  const oldLookup = deferred();
  apiMock.activeValidation.mockImplementation((id) =>
    id === "connection-a" ? oldLookup.promise : Promise.resolve(run("run-b")),
  );
  const { result, rerender } = renderValidation();

  rerender({ connectionId: "connection-b" });
  await waitFor(() => expect(result.current.run?.id).toBe("run-b"));
  await act(async () => oldLookup.resolve(run("run-a")));

  expect(result.current.run?.id).toBe("run-b");
  expect(sources).toHaveLength(1);
  expect(sources[0].url).toBe("/validation/run-b");
  expect(notify).not.toHaveBeenCalled();
});

test("手动启动的新验证不会被较慢的活动验证查询覆盖", async () => {
  const lookup = deferred();
  apiMock.activeValidation.mockReturnValue(lookup.promise);
  const { result } = renderValidation();

  act(() => {
    expect(result.current.showRun(run("new-run"), "connection-a")).toBe(true);
  });
  await act(async () => lookup.resolve(run("old-run")));

  expect(result.current.run?.id).toBe("new-run");
  expect(sources).toHaveLength(1);
});

test("切换连接后不接受旧连接迟到的启动结果", async () => {
  const { result, rerender } = renderValidation();
  rerender({ connectionId: "connection-b" });

  act(() => {
    expect(result.current.showRun(run("old-run"), "connection-a")).toBe(false);
  });

  expect(result.current.run).toBeNull();
  expect(sources).toHaveLength(0);
});

test("切换运行和关闭详情后，旧详情响应不更新页面或通知", async () => {
  const oldRefresh = deferred();
  apiMock.validationRun.mockReturnValue(oldRefresh.promise);
  const { result } = renderValidation();
  act(() => result.current.showRun(run("run-a"), "connection-a"));
  act(() => sources[0].emit("validation", { id: 1, message: "进行中" }));
  await waitFor(() => expect(apiMock.validationRun).toHaveBeenCalledWith("run-a"));

  act(() => result.current.showRun(run("run-b"), "connection-a"));
  expect(sources[0].closed).toBe(true);
  await act(async () => oldRefresh.resolve(run("run-a", "passed")));
  expect(result.current.run?.id).toBe("run-b");
  expect(result.current.events).toEqual([]);
  expect(onCompleted).not.toHaveBeenCalled();

  act(() => result.current.clearRun());
  expect(sources[1].closed).toBe(true);
  expect(result.current.run).toBeNull();
  expect(notify).not.toHaveBeenCalled();
});

test("详情刷新失败后可由下一事件恢复，完成回调只执行一次", async () => {
  apiMock.validationRun
    .mockRejectedValueOnce(new Error("验证详情读取失败"))
    .mockResolvedValue(run("run-a", "passed"));
  const { result } = renderValidation();
  act(() => result.current.showRun(run("run-a"), "connection-a"));
  const source = sources[0];
  expect(source.options).toEqual({ withCredentials: true });

  act(() => source.emit("validation", { id: 1, message: "开始" }));
  await waitFor(() => expect(notify).toHaveBeenCalledWith("验证详情读取失败", "error"));
  act(() => source.emit("validation", { id: 2, message: "完成" }));
  await waitFor(() => expect(result.current.run?.status).toBe("passed"));
  act(() => source.emit("close"));

  expect(apiMock.validationRun).toHaveBeenCalledTimes(2);
  expect(onCompleted).toHaveBeenCalledTimes(1);
  expect(notify).toHaveBeenCalledWith("模型验证通过", "success");
  expect(source.closed).toBe(true);
});

test("结束事件会读取最终失败状态并刷新配置", async () => {
  apiMock.validationRun.mockResolvedValue(run("run-a", "failed"));
  const { result } = renderValidation();
  act(() => result.current.showRun(run("run-a"), "connection-a"));

  act(() => sources[0].emit("close"));
  await waitFor(() => expect(result.current.run?.status).toBe("failed"));

  expect(onCompleted).toHaveBeenCalledTimes(1);
  expect(notify).toHaveBeenCalledWith("模型验证失败", "error");
  expect(sources[0].closed).toBe(true);
});

test("卸载时关闭事件流并停止计时", async () => {
  const clearInterval = vi.spyOn(window, "clearInterval");
  const { result, unmount } = renderValidation();
  act(() => result.current.showRun(run("run-a"), "connection-a"));
  expect(sources).toHaveLength(1);

  unmount();

  expect(sources[0].closed).toBe(true);
  expect(clearInterval).toHaveBeenCalled();
  clearInterval.mockRestore();
});
