import { apiMock } from "./product-flow-mocks";
import { beforeAll, expect, test, vi } from "vitest";
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithServerState as render } from "./renderWithServerState";
import { App } from "../src/App";
import { ApiError } from "../src/api";
import { AuthPages } from "../src/pages/AuthPages";
import { SESSION_EXPIRED_EVENT } from "../src/shared/api/request";

beforeAll(async () => {
  // 会话断言从首页依赖就绪后开始，不将并行编译耗时混入页面等待窗口。
  await import("../src/features/workbench/WorkbenchPage");
});

const confirmedUser = {
  id: "synthetic-user",
  email: "preview@example.test",
  display_name: "合成用户",
};
const httpError = (status) => Object.assign(new ApiError("合成请求失败"), { status });

test.each([
  ["网络中断", new TypeError("合成网络中断")],
  ["服务暂不可用", httpError(503)],
  ["身份请求403", httpError(403)],
])("身份请求%s不误判未登录，重试成功后才挂载应用", async (_name, error) => {
  apiMock.me.mockRejectedValueOnce(error).mockResolvedValueOnce(confirmedUser);
  render(<App />);
  expect(await screen.findByText("无法连接智能体工作台")).toBeVisible();
  expect(screen.queryByRole("heading", { name: "登录" })).not.toBeInTheDocument();
  expect(screen.queryByRole("navigation", { name: "主导航" })).not.toBeInTheDocument();
  expect(apiMock.status).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "重试连接" }));
  expect(await screen.findByRole("heading", { name: "首页" })).toBeVisible();
  expect(screen.getByText("合成用户")).toBeVisible();
  expect(apiMock.me).toHaveBeenCalledTimes(2);
});

test("身份请求401仍显示登录且不读取受保护状态", async () => {
  apiMock.me.mockRejectedValue(httpError(401));
  render(<App />);
  expect(await screen.findByRole("heading", { name: "登录" })).toBeVisible();
  expect(screen.queryByText("无法连接智能体工作台")).not.toBeInTheDocument();
  expect(apiMock.status).not.toHaveBeenCalled();
});

test("身份确认后状态慢请求不阻断页面，失败可单独重试", async () => {
  apiMock.me.mockResolvedValue(confirmedUser);
  let failStatus;
  apiMock.status.mockImplementationOnce(
    () =>
      new Promise((_, reject) => {
        failStatus = reject;
      }),
  );
  render(<App />);
  expect(await screen.findByRole("heading", { name: "首页" })).toBeVisible();
  expect(screen.getByText("合成用户")).toBeVisible();
  expect(
    screen.getByRole("button", { name: /我的运行 Listing 数量暂不可用/ }),
  ).toHaveTextContent("—/3");
  await act(async () => failStatus(httpError(503)));
  expect(screen.getByText("系统状态读取失败。")).toBeVisible();
  expect(screen.getByRole("heading", { name: "首页" })).toBeVisible();
  let finishStatus;
  apiMock.status.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finishStatus = resolve;
      }),
  );
  await userEvent.click(screen.getByRole("button", { name: "重试系统状态" }));
  expect(screen.getByRole("button", { name: "重试中…" })).toBeDisabled();
  await act(async () => finishStatus({ warnings: [], my_running_segments: 1 }));
  await waitFor(() =>
    expect(screen.queryByText("系统状态读取失败。")).not.toBeInTheDocument(),
  );
  expect(screen.getByRole("button", { name: /我的运行 Listing 1\/3/ })).toBeVisible();
  expect(apiMock.me).toHaveBeenCalledTimes(1);
});

test("后续状态读取失败保留已确认身份与上次状态", async () => {
  apiMock.me.mockResolvedValue(confirmedUser);
  apiMock.status.mockResolvedValue({ warnings: [], my_running_segments: 2 });
  render(<App />);
  const capacity = await screen.findByRole("button", { name: /我的运行 Listing 2\/3/ });
  apiMock.status.mockRejectedValueOnce(httpError(503));
  await userEvent.click(capacity);
  expect(await screen.findByText("系统状态读取失败，当前显示上次状态。")).toBeVisible();
  expect(screen.getByText("合成用户")).toBeVisible();
  expect(screen.getByRole("button", { name: /我的运行 Listing 2\/3/ })).toBeVisible();
  expect(screen.queryByRole("heading", { name: "登录" })).not.toBeInTheDocument();
});

test("已确认身份之后状态401仍结束会话", async () => {
  apiMock.me.mockResolvedValue(confirmedUser);
  apiMock.status.mockRejectedValue(httpError(401));
  render(<App />);
  expect(await screen.findByRole("heading", { name: "登录" })).toBeVisible();
  expect(screen.queryByRole("navigation", { name: "主导航" })).not.toBeInTheDocument();
});

test("任意子页面会话失效后退出已登录应用壳", async () => {
  apiMock.me.mockResolvedValue({
    id: "user-1",
    email: "admin@example.com",
    display_name: "管理员",
  });

  render(<App />);
  expect(await screen.findByRole("heading", { name: "首页" })).toBeVisible();

  act(() => window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT)));

  expect(await screen.findByRole("heading", { name: "登录" })).toBeVisible();
  expect(screen.queryByRole("navigation", { name: "主导航" })).not.toBeInTheDocument();
});

test("已登录用户访问公开认证路由时返回首页", async () => {
  window.location.hash = "#register?token=unused-token";
  apiMock.me.mockResolvedValue({
    id: "user-1",
    email: "admin@example.com",
    display_name: "管理员",
  });

  render(<App />);

  expect(await screen.findByRole("heading", { name: "首页" })).toBeVisible();
  expect(window.location.hash).toBe("#workbench");
  expect(apiMock.validateInvitation).not.toHaveBeenCalled();
});

test("邮箱验证页确认后结束旧会话并返回登录", async () => {
  const user = userEvent.setup();
  const onSessionEnded = vi.fn();
  apiMock.validateEmailChange.mockResolvedValue({
    email: "wch@seekwaygroup.com",
    expires_at: "2026-09-20T10:30:00Z",
  });
  apiMock.completeEmailChange.mockResolvedValue(null);

  render(
    <AuthPages
      route={{ page: "change-email", query: { token: "email-token" } }}
      onLogin={vi.fn()}
      onSessionEnded={onSessionEnded}
    />,
  );

  expect(
    await screen.findByRole("heading", { name: "确认修改登录邮箱" }),
  ).toBeVisible();
  expect(screen.getByText(/@seekwaygroup.com/)).toBeVisible();
  await user.click(screen.getByRole("button", { name: "确认修改邮箱" }));

  await waitFor(() => {
    expect(apiMock.completeEmailChange).toHaveBeenCalledWith("email-token");
    expect(onSessionEnded).toHaveBeenCalledTimes(1);
    expect(window.location.hash).toContain("#login?notice=email-changed");
  });
});
