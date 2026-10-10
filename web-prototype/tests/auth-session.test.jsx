import { apiMock } from "./product-flow-mocks";
import { expect, test, vi } from "vitest";
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithServerState as render } from "./renderWithServerState";
import { App } from "../src/App";
import { AuthPages } from "../src/pages/AuthPages";
import { SESSION_EXPIRED_EVENT } from "../src/shared/api/request";

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
