import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    configs: vi.fn(),
    activeValidation: vi.fn(),
  },
}));

vi.mock("../src/api", () => ({ api: apiMock }));

import { ApiManagement } from "../src/pages/ApiManagement";

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function connection(id) {
  return {
    id,
    name: id,
    provider: "responses-compatible",
    active_version_id: null,
    active_version: null,
    versions: [],
    models: [],
  };
}

const notify = vi.fn();

beforeEach(() => {
  apiMock.configs.mockReset();
  apiMock.activeValidation.mockReset().mockResolvedValue(null);
  notify.mockReset();
});

afterEach(() => cleanup());

test("较早的配置响应晚到时不覆盖当前连接", async () => {
  const oldRequest = deferred();
  const newRequest = deferred();
  apiMock.configs
    .mockReturnValueOnce(oldRequest.promise)
    .mockReturnValueOnce(newRequest.promise);

  const { rerender } = render(
    <ApiManagement notify={notify} focusConnectionId="old" />,
  );
  rerender(<ApiManagement notify={notify} focusConnectionId="new" />);

  await act(async () => newRequest.resolve([connection("new")]));
  expect(screen.getByRole("heading", { name: "new" })).toBeVisible();
  await act(async () => oldRequest.resolve([connection("old")]));

  expect(screen.getByRole("heading", { name: "new" })).toBeVisible();
  expect(screen.queryByRole("heading", { name: "old" })).not.toBeInTheDocument();
});

test("较早的读取失败晚到时不覆盖成功页面或弹出错误", async () => {
  const oldRequest = deferred();
  const newRequest = deferred();
  apiMock.configs
    .mockReturnValueOnce(oldRequest.promise)
    .mockReturnValueOnce(newRequest.promise);

  const { rerender } = render(
    <ApiManagement notify={notify} focusConnectionId="old" />,
  );
  rerender(<ApiManagement notify={notify} focusConnectionId="new" />);

  await act(async () => newRequest.resolve([connection("new")]));
  await act(async () => oldRequest.reject(new Error("旧请求失败")));

  expect(screen.getByRole("heading", { name: "new" })).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(notify).not.toHaveBeenCalled();
});

test("较新的读取失败时，迟到的旧成功不能伪装为已加载", async () => {
  const oldRequest = deferred();
  const newRequest = deferred();
  apiMock.configs
    .mockReturnValueOnce(oldRequest.promise)
    .mockReturnValueOnce(newRequest.promise);

  const { rerender } = render(
    <ApiManagement notify={notify} focusConnectionId="old" />,
  );
  rerender(<ApiManagement notify={notify} focusConnectionId="new" />);

  await act(async () => newRequest.reject(new Error("当前读取失败")));
  await act(async () => oldRequest.resolve([connection("old")]));

  expect(screen.getByRole("alert")).toHaveTextContent("当前读取失败");
  expect(screen.queryByRole("heading", { name: "old" })).not.toBeInTheDocument();
  expect(notify).toHaveBeenCalledWith("当前读取失败", "error");
});

test("页面卸载后忽略尚未返回的配置读取", async () => {
  const pending = deferred();
  apiMock.configs.mockReturnValue(pending.promise);
  const { unmount } = render(<ApiManagement notify={notify} />);

  unmount();
  await act(async () => pending.reject(new Error("页面已离开")));

  expect(notify).not.toHaveBeenCalled();
});
