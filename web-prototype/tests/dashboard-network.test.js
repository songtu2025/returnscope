import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { dashboardApi } from "../src/shared/api/dashboardApi";
import {
  resetSessionExpiration,
  SESSION_EXPIRED_EVENT,
} from "../src/shared/api/request";

const dashboardResponse = () =>
  new Response(JSON.stringify({ id: "dashboard-1" }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });

beforeEach(() => resetSessionExpiration());

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("看板只读请求遇到一次网络中断后重试成功", async () => {
  vi.useFakeTimers();
  const fetchMock = vi
    .fn()
    .mockRejectedValueOnce(new TypeError("Failed to fetch"))
    .mockResolvedValueOnce(dashboardResponse());
  vi.stubGlobal("fetch", fetchMock);

  const pending = dashboardApi.analysisDashboard("dashboard-1", "version-1");
  await vi.advanceTimersByTimeAsync(300);

  await expect(pending).resolves.toEqual({ id: "dashboard-1" });
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(fetchMock.mock.calls[0][1].method).toBeUndefined();
});

test("持续网络中断只重试一次并返回可执行的提示", async () => {
  vi.useFakeTimers();
  const fetchMock = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
  vi.stubGlobal("fetch", fetchMock);

  const pending = dashboardApi.analysisDashboardInsights("dashboard-1", "version-1");
  const failure = expect(pending).rejects.toThrow("网络连接中断，请检查网络后重新加载");
  await vi.advanceTimersByTimeAsync(300);

  await failure;
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("HTTP 5xx 不作为网络中断重试", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ detail: "服务暂不可用" }), {
      status: 503,
      headers: { "content-type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);

  await expect(
    dashboardApi.analysisDashboard("dashboard-1", "version-1"),
  ).rejects.toMatchObject({ status: 503 });
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("HTTP 401 仍走现有会话失效流程且不重试", async () => {
  const listener = vi.fn();
  window.addEventListener(SESSION_EXPIRED_EVENT, listener);
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ detail: "登录已失效" }), {
      status: 401,
      headers: { "content-type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);

  try {
    await expect(
      dashboardApi.analysisDashboard("dashboard-1", "version-1"),
    ).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenCalledTimes(1);
  } finally {
    window.removeEventListener(SESSION_EXPIRED_EVENT, listener);
  }
});

test("路由取消请求后不发出第二次读取", async () => {
  vi.useFakeTimers();
  const controller = new AbortController();
  const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError("Failed to fetch"));
  vi.stubGlobal("fetch", fetchMock);

  const pending = dashboardApi.analysisDashboard("dashboard-1", "version-1", {
    signal: controller.signal,
  });
  const failure = expect(pending).rejects.toMatchObject({ name: "AbortError" });
  await vi.advanceTimersByTimeAsync(0);
  controller.abort();
  await vi.advanceTimersByTimeAsync(300);

  await failure;
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("写入请求遇到网络中断不自动重试", async () => {
  const fetchMock = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
  vi.stubGlobal("fetch", fetchMock);

  await expect(dashboardApi.createAnalysisDashboard({})).rejects.toThrow(
    "Failed to fetch",
  );
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[0][1].method).toBe("POST");
});
