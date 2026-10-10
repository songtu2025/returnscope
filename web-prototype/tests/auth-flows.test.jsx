import { apiMock } from "./product-flow-mocks";
import { expect, test } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithServerState as render } from "./renderWithServerState";
import { App } from "../src/App";

test("用户登录后进入任务工作台", async () => {
  const user = userEvent.setup();
  apiMock.me.mockRejectedValue(new Error("未登录"));
  apiMock.login.mockResolvedValue({
    id: "user-1",
    email: "admin@example.com",
    display_name: "管理员",
  });

  render(<App />);

  expect(await screen.findByRole("heading", { name: "登录" })).toBeVisible();
  expect(screen.queryByText("仅限受邀成员")).not.toBeInTheDocument();
  expect(document.querySelector(".login-card .login-icon")).not.toBeInTheDocument();
  expect(screen.getByText("用户语义分析智能体")).toBeVisible();
  expect(screen.queryByText("后台持续运行")).not.toBeInTheDocument();
  expect(screen.queryByText("配置与数据快照")).not.toBeInTheDocument();
  expect(screen.queryByText("全流程修改留痕")).not.toBeInTheDocument();
  expect(
    screen.queryByText(/数据版本、模型运行、人工复核与结果交付集中在一个工作台/),
  ).not.toBeInTheDocument();
  await user.type(screen.getByLabelText("邮箱"), "admin@example.com");
  await user.type(screen.getByLabelText("密码"), "secure-password");
  await user.click(screen.getByRole("button", { name: /进入工作台/ }));

  await waitFor(() =>
    expect(apiMock.login).toHaveBeenCalledWith("admin@example.com", "secure-password"),
  );
  expect(await screen.findByRole("navigation", { name: "主导航" })).toBeVisible();
});

test("登录页可申请密码重置且不泄露账号是否存在", async () => {
  const user = userEvent.setup();
  apiMock.me.mockRejectedValue(new Error("未登录"));
  apiMock.requestPasswordReset.mockResolvedValue(null);

  render(<App />);

  await user.click(await screen.findByRole("button", { name: "忘记密码？" }));
  expect(window.location.hash).toBe("#forgot-password");
  await user.type(screen.getByLabelText("邮箱"), "member@example.com");
  await user.click(screen.getByRole("button", { name: /发送重置链接/ }));

  expect(apiMock.requestPasswordReset).toHaveBeenCalledWith("member@example.com");
  expect(await screen.findByRole("heading", { name: "请检查邮箱" })).toBeVisible();
  expect(screen.getByText(/如果该邮箱对应可用账号/)).toBeVisible();
});

test("受邀成员验证链接后设置账号并进入工作台", async () => {
  const user = userEvent.setup();
  window.location.hash = "#register?token=invitation-token-value";
  apiMock.me.mockRejectedValue(new Error("未登录"));
  apiMock.validateInvitation.mockResolvedValue({ email: "member@example.com" });
  apiMock.register.mockResolvedValue({
    id: "user-2",
    email: "member@example.com",
    display_name: "测试成员",
  });

  render(<App />);

  expect(await screen.findByDisplayValue("member@example.com")).toHaveAttribute(
    "readonly",
  );
  await user.type(screen.getByLabelText("姓名"), "测试成员");
  await user.type(screen.getByLabelText(/^密码$/), "member-password-123");
  await user.type(screen.getByLabelText("确认密码"), "member-password-123");
  await user.click(screen.getByRole("button", { name: /注册并进入工作台/ }));

  expect(apiMock.register).toHaveBeenCalledWith({
    token: "invitation-token-value",
    display_name: "测试成员",
    password: "member-password-123",
  });
  expect(await screen.findByRole("navigation", { name: "主导航" })).toBeVisible();
  expect(window.location.hash).toBe("#workbench");
});

test("密码重置成功后返回登录页并显示确认信息", async () => {
  const user = userEvent.setup();
  window.location.hash = "#reset-password?token=reset-token-value";
  apiMock.me.mockRejectedValue(new Error("未登录"));
  apiMock.validatePasswordReset.mockResolvedValue({ valid: true });
  apiMock.completePasswordReset.mockResolvedValue(null);

  render(<App />);

  await screen.findByRole("heading", { name: "设置新密码" });
  await user.type(screen.getByLabelText("新密码"), "new-password-123");
  await user.type(screen.getByLabelText("确认新密码"), "new-password-123");
  await user.click(screen.getByRole("button", { name: /更新密码/ }));

  expect(apiMock.completePasswordReset).toHaveBeenCalledWith({
    token: "reset-token-value",
    new_password: "new-password-123",
  });
  expect(await screen.findByText("密码已重置，请使用新密码登录。")).toBeVisible();
  expect(window.location.hash).toContain("#login?notice=password-reset");
});
