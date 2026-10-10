import { apiMock } from "./product-flow-mocks";
import { expect, test, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithServerState as render } from "./renderWithServerState";
import { TeamPage } from "../src/pages/TeamPage";

test("用户账号超过五个时仍可继续邀请", async () => {
  apiMock.users.mockResolvedValue(
    Array.from({ length: 6 }, (_, index) => ({
      id: `user-${index + 1}`,
      display_name: `成员 ${index + 1}`,
      email: `member${index + 1}@example.com`,
      active: true,
    })),
  );

  render(
    <TeamPage
      notify={vi.fn()}
      currentUser={{ id: "user-1", display_name: "成员 1" }}
    />,
  );

  expect(await screen.findByText("6 个启用账号 · 0 个待注册")).toBeVisible();
  expect(screen.getByRole("button", { name: "邀请用户" })).toBeEnabled();
  expect(screen.queryByText(/席位|人数上限/)).not.toBeInTheDocument();
});

test("用户与安全仅在邀请邮箱和密码表单完成后启用主操作", async () => {
  const user = userEvent.setup();
  apiMock.users.mockResolvedValue([
    {
      id: "user-1",
      display_name: "管理员",
      email: "admin@example.com",
      active: true,
    },
  ]);
  render(
    <TeamPage
      notify={vi.fn()}
      currentUser={{ id: "user-1", display_name: "管理员" }}
    />,
  );

  await user.click(await screen.findByRole("button", { name: "邀请用户" }));
  const inviteButton = await screen.findByRole("button", {
    name: "发送邀请",
  });
  expect(inviteButton).toBeDisabled();
  expect(screen.getByText("请填写有效邮箱。")).toBeVisible();

  await user.type(screen.getByLabelText("邮箱"), "invalid-email");
  expect(inviteButton).toBeDisabled();
  expect(screen.getByText("请填写有效邮箱。")).toBeVisible();

  await user.clear(screen.getByLabelText("邮箱"));
  await user.type(screen.getByLabelText("邮箱"), "member@example.com");
  expect(inviteButton).toBeEnabled();

  await user.click(screen.getByRole("button", { name: "取消" }));
  await user.click(screen.getByRole("button", { name: "修改密码" }));
  const updatePasswordButton = await screen.findByRole("button", {
    name: "保存并重新登录",
  });
  expect(updatePasswordButton).toBeDisabled();
  expect(screen.getByText("请填写当前密码。")).toBeVisible();

  await user.type(screen.getByLabelText("当前密码"), "old-password");
  await user.type(screen.getByLabelText(/^新密码/), "12345678901");
  expect(updatePasswordButton).toBeDisabled();
  expect(screen.getByText("新密码至少 12 位。")).toBeVisible();

  await user.type(screen.getByLabelText(/^新密码/), "0");
  expect(updatePasswordButton).toBeEnabled();
});

test("当前用户验证密码后可以申请修改登录邮箱", async () => {
  const user = userEvent.setup();
  apiMock.users.mockResolvedValue([
    {
      id: "user-1",
      display_name: "管理员",
      email: "admin@example.com",
      active: true,
    },
  ]);
  apiMock.requestEmailChange.mockResolvedValue(null);

  render(
    <TeamPage
      notify={vi.fn()}
      currentUser={{
        id: "user-1",
        display_name: "管理员",
        email: "admin@example.com",
      }}
    />,
  );

  await user.click(await screen.findByRole("button", { name: "修改邮箱" }));
  const sendButton = screen.getByRole("button", { name: "发送验证邮件" });
  expect(sendButton).toBeDisabled();
  await user.type(screen.getByLabelText("新邮箱"), "WCH@SeekwayGroup.com");
  await user.type(screen.getByLabelText("邮箱修改当前密码"), "current-password");
  expect(sendButton).toBeEnabled();
  await user.click(sendButton);

  expect(apiMock.requestEmailChange).toHaveBeenCalledWith({
    current_password: "current-password",
    new_email: "wch@seekwaygroup.com",
  });
  expect(await screen.findByText(/验证邮件已发送至/)).toHaveTextContent(
    "wch@seekwaygroup.com",
  );
});

test("待注册邀请可重新发送和撤销", async () => {
  const user = userEvent.setup();
  apiMock.invitations.mockResolvedValue([
    {
      id: "invitation-1",
      email: "member@example.com",
      expires_at: "2026-09-21T08:00:00Z",
      created_at: "2026-09-20T08:00:00Z",
      created_by: "user-1",
    },
  ]);
  apiMock.resendInvitation.mockResolvedValue({ id: "invitation-2" });
  apiMock.revokeInvitation.mockResolvedValue(null);

  render(
    <TeamPage
      notify={vi.fn()}
      currentUser={{ id: "user-1", display_name: "管理员" }}
    />,
  );

  expect(await screen.findByText("member@example.com")).toBeVisible();
  expect(screen.getByText("0 个启用账号 · 1 个待注册")).toBeVisible();

  await user.click(screen.getByRole("button", { name: "重新发送" }));
  expect(apiMock.resendInvitation).toHaveBeenCalledWith("invitation-1");

  await user.click(screen.getByRole("button", { name: "撤销" }));
  expect(apiMock.revokeInvitation).toHaveBeenCalledWith("invitation-1");
});
