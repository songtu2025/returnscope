import { afterEach, beforeEach, expect, test, vi } from "vitest";

import {
  request,
  queryString,
  ApiError,
  resetSessionExpiration,
  SESSION_EXPIRED_EVENT,
} from "../src/shared/api/request";
import { resultExportApi } from "../src/shared/api/resultExportApi";

beforeEach(() => {
  resetSessionExpiration();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("任意业务请求收到 401 时统一且只触发一次会话失效", async () => {
  const listener = vi.fn();
  window.addEventListener(SESSION_EXPIRED_EVENT, listener);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: "登录已失效" }), {
          status: 401,
          headers: { "content-type": "application/json" },
        }),
      ),
    ),
  );

  await expect(request("/api/tasks")).rejects.toMatchObject({ status: 401 });
  await expect(request("/api/users")).rejects.toMatchObject({ status: 401 });
  expect(listener).toHaveBeenCalledTimes(1);

  window.removeEventListener(SESSION_EXPIRED_EVENT, listener);
});

test("登录凭据错误不会触发已登录会话失效事件", async () => {
  const listener = vi.fn();
  window.addEventListener(SESSION_EXPIRED_EVENT, listener);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "邮箱或密码错误" }), {
        status: 401,
        headers: { "content-type": "application/json" },
      }),
    ),
  );

  await expect(request("/api/auth/login")).rejects.toMatchObject({ status: 401 });
  expect(listener).not.toHaveBeenCalled();

  window.removeEventListener(SESSION_EXPIRED_EVENT, listener);
});

test("JSON 错误对象缺少 detail 时保持通用错误文案", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ code: "BAD_REQUEST" }), {
        status: 400,
        headers: { "content-type": "application/json" },
      }),
    ),
  );

  await expect(request("/api/tasks")).rejects.toMatchObject({
    message: "请求失败",
    status: 400,
  });
});

test.each([
  [{ detail: "合成错误" }, "合成错误"],
  [{ detail: 0 }, "请求失败"],
  [{ detail: false }, "请求失败"],
  [{ detail: null }, "请求失败"],
  [{ detail: [] }, ""],
  [
    { detail: [{ msg: "甲" }, { msg: 0 }, null, "乙", { msg: false }] },
    "甲；0；；；false",
  ],
  [{ detail: [{ msg: null }, {}] }, "；"],
  [null, "请求失败"],
  [false, "请求失败"],
  ["合成原始错误", "合成原始错误"],
])("错误载荷 %# 保留文案和状态", async (payload, message) => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 422,
        headers: { "content-type": "application/json" },
      }),
    ),
  );
  const pending = request("/api/synthetic");
  await expect(pending).rejects.toBeInstanceOf(ApiError);
  await expect(pending).rejects.toMatchObject({
    message,
    status: 422,
  });
});

test("非 JSON 文本和大小写不匹配的媒体类型保持文本解析", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response('{"detail":"合成错误"}', {
        status: 400,
        headers: { "content-type": "Application/JSON" },
      }),
    ),
  );
  await expect(request("/api/synthetic")).rejects.toMatchObject({
    message: '{"detail":"合成错误"}',
    status: 400,
  });
});

test("JSON 解析失败优先于 401 会话通知且保留原异常", async () => {
  const listener = vi.fn();
  const failure = new SyntaxError("合成解析失败");
  window.addEventListener(SESSION_EXPIRED_EVENT, listener);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      status: 401,
      ok: false,
      headers: new Headers({ "content-type": "application/json" }),
      json: vi.fn().mockRejectedValue(failure),
    }),
  );
  try {
    await expect(request("/api/synthetic")).rejects.toBe(failure);
    expect(listener).not.toHaveBeenCalled();
  } finally {
    window.removeEventListener(SESSION_EXPIRED_EVENT, listener);
  }
});

test.each(["/api/auth/login", "/api/auth/me", "/api/auth/register"])(
  "%s 成功后重新允许一次会话失效通知",
  async (path) => {
    const listener = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, listener);
    const unauthorized = () => new Response("合成失效", { status: 401 });
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(unauthorized())
        .mockResolvedValueOnce(new Response("合成成功"))
        .mockResolvedValueOnce(unauthorized()),
    );
    try {
      await expect(request("/api/synthetic")).rejects.toMatchObject({ status: 401 });
      expect(await request(path)).toBe("合成成功");
      await expect(request("/api/synthetic")).rejects.toMatchObject({ status: 401 });
      expect(listener).toHaveBeenCalledTimes(2);
    } finally {
      window.removeEventListener(SESSION_EXPIRED_EVENT, listener);
    }
  },
);

test("204 不读载荷且不重置会话通知", async () => {
  const listener = vi.fn();
  const json = vi.fn();
  window.addEventListener(SESSION_EXPIRED_EVENT, listener);
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce(new Response("合成失效", { status: 401 }))
      .mockResolvedValueOnce({ status: 204, json })
      .mockResolvedValueOnce(new Response("合成失效", { status: 401 })),
  );
  try {
    await expect(request("/api/synthetic")).rejects.toMatchObject({ status: 401 });
    expect(await request("/api/auth/me")).toBeNull();
    await expect(request("/api/synthetic")).rejects.toMatchObject({ status: 401 });
    expect(json).not.toHaveBeenCalled();
    expect(listener).toHaveBeenCalledTimes(1);
  } finally {
    window.removeEventListener(SESSION_EXPIRED_EVENT, listener);
  }
});

test.each([new DOMException("合成取消", "AbortError"), new TypeError("合成网络失败")])(
  "请求失败保留原异常对象",
  async (failure) => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(failure));
    await expect(request("/api/synthetic")).rejects.toBe(failure);
  },
);

test("查询参数、凭据覆盖和 FormData 请求头保持原约定", async () => {
  expect(
    queryString({ empty: "", missing: null, unset: undefined, zero: 0, flag: false }),
  ).toBe("?zero=0&flag=false");
  const fetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetch);
  const body = new FormData();
  await request("/api/synthetic", {
    body,
    credentials: "omit",
    headers: { "X-Synthetic": "yes" },
  });
  expect(fetch.mock.calls[0][1]).toEqual({
    body,
    credentials: "omit",
    headers: { "X-Synthetic": "yes" },
  });
});

test("文件下载与普通请求共用一次登录失效通知", async () => {
  const listener = vi.fn();
  window.addEventListener(SESSION_EXPIRED_EVENT, listener);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: "登录已失效" }), {
          status: 401,
          headers: { "content-type": "application/json" },
        }),
      ),
    ),
  );
  try {
    await expect(resultExportApi.save({ id: "job-1" })).rejects.toMatchObject({
      status: 401,
      message: "登录已失效",
    });
    await expect(request("/api/tasks")).rejects.toMatchObject({ status: 401 });
    expect(listener).toHaveBeenCalledTimes(1);
  } finally {
    window.removeEventListener(SESSION_EXPIRED_EVENT, listener);
  }
});

test.each([
  [403, "无权下载此文件"],
  [404, "导出已过期，请重新生成"],
  [409, "导出尚未完成"],
  [500, "导出服务暂时不可用"],
])("文件下载失败 %s 保留业务文案和状态", async (status, message) => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: message }), {
        status,
        headers: { "content-type": "application/json" },
      }),
    ),
  );
  await expect(resultExportApi.save({ id: "job-1" })).rejects.toMatchObject({
    status,
    message,
  });
});

test("正常文件按二进制下载并携带登录凭据", async () => {
  vi.useFakeTimers();
  const blob = new Blob(["合成导出内容"]);
  const fetch = vi
    .fn()
    .mockResolvedValue({ status: 200, ok: true, blob: async () => blob });
  vi.stubGlobal("fetch", fetch);
  const create = vi.fn().mockReturnValue("blob:synthetic-export");
  vi.stubGlobal("URL", { createObjectURL: create, revokeObjectURL: vi.fn() });
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => {});
  try {
    await resultExportApi.save({ id: "job-1", filename: "合成结果.xlsx" });
    expect(create).toHaveBeenCalledWith(blob);
    expect(fetch).toHaveBeenCalledWith(
      "/api/result-exports/job-1/file",
      expect.objectContaining({ credentials: "include" }),
    );
    expect(click.mock.instances[0].download).toBe("合成结果.xlsx");
    vi.runAllTimers();
  } finally {
    click.mockRestore();
    vi.useRealTimers();
  }
});
