import userEvent from "@testing-library/user-event";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    configs: vi.fn(),
    activeValidation: vi.fn(),
  },
}));

vi.mock("../src/shared/api/modelApi", () => ({ modelApi: apiMock }));

import { ModelServicePage } from "../src/features/system-settings/ModelServicePage";

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
    <ModelServicePage notify={notify} focusConnectionId="old" />,
  );
  rerender(<ModelServicePage notify={notify} focusConnectionId="new" />);

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
    <ModelServicePage notify={notify} focusConnectionId="old" />,
  );
  rerender(<ModelServicePage notify={notify} focusConnectionId="new" />);

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
    <ModelServicePage notify={notify} focusConnectionId="old" />,
  );
  rerender(<ModelServicePage notify={notify} focusConnectionId="new" />);

  await act(async () => newRequest.reject(new Error("当前读取失败")));
  await act(async () => oldRequest.resolve([connection("old")]));

  expect(screen.getByRole("alert")).toHaveTextContent("当前读取失败");
  expect(screen.queryByRole("heading", { name: "old" })).not.toBeInTheDocument();
  expect(notify).toHaveBeenCalledWith("当前读取失败", "error");
});

test("页面卸载后忽略尚未返回的配置读取", async () => {
  const pending = deferred();
  apiMock.configs.mockReturnValue(pending.promise);
  const { unmount } = render(<ModelServicePage notify={notify} />);

  unmount();
  await act(async () => pending.reject(new Error("页面已离开")));

  expect(notify).not.toHaveBeenCalled();
});

test("模型服务加载完成前不显示未创建状态", async () => {
  let resolveConfigs;
  apiMock.configs.mockReturnValue(
    new Promise((resolve) => {
      resolveConfigs = resolve;
    }),
  );

  render(<ModelServicePage notify={vi.fn()} />);

  expect(screen.getByText("正在读取模型服务…")).toBeVisible();
  expect(screen.queryByText("尚未创建模型服务")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "新增模型服务" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByText("0 个可用模型")).not.toBeInTheDocument();

  await act(async () => {
    resolveConfigs([
      {
        id: "conn-1",
        name: "sub2api",
        provider: "responses-compatible",
        active_version_id: "cfg-1",
        active_version: {
          id: "cfg-1",
          version: 4,
          base_url: "https://api.example.com/v1",
          validation_status: "validated",
        },
        versions: [],
        models: [],
      },
    ]);
  });

  expect(await screen.findByRole("heading", { name: "sub2api" })).toBeVisible();
  expect(screen.queryByText("正在读取模型服务…")).not.toBeInTheDocument();
});

test("模型服务只有读取成功后才显示真实空状态", async () => {
  apiMock.configs.mockResolvedValue([]);

  render(<ModelServicePage notify={vi.fn()} />);

  expect(await screen.findByText("尚未创建模型服务")).toBeVisible();
  expect(screen.getByRole("button", { name: "新增模型服务" })).toBeVisible();
  expect(screen.queryByText("正在读取模型服务…")).not.toBeInTheDocument();
});

test("模型服务读取失败时显示重试且不伪装为空状态", async () => {
  const user = userEvent.setup();
  apiMock.configs
    .mockRejectedValueOnce(new Error("模型服务暂时不可用"))
    .mockResolvedValueOnce([]);

  render(<ModelServicePage notify={vi.fn()} />);

  expect(await screen.findByRole("alert")).toHaveTextContent("模型服务暂时不可用");
  expect(screen.queryByText("尚未创建模型服务")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "重新加载" }));
  expect(await screen.findByText("尚未创建模型服务")).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
