import { afterEach, beforeEach, expect, test, vi } from "vitest";

import {
  request,
  resetSessionExpiration,
  SESSION_EXPIRED_EVENT,
} from "../src/shared/api/request";

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
