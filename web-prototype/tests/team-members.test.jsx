import { apiMock } from "./product-flow-mocks";
import { expect, test, vi } from "vitest";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithServerState as render } from "./renderWithServerState";
import { TeamPage } from "../src/pages/TeamPage";

test("用户设置首屏使用用户与安全标题", async () => {
  render(
    <TeamPage
      notify={vi.fn()}
      currentUser={{ id: "user-1", display_name: "管理员" }}
    />,
  );

  expect(await screen.findByRole("heading", { name: "用户与安全" })).toBeVisible();
  expect(screen.getByText("访问控制台")).toBeVisible();
  expect(screen.getByRole("table", { name: "团队成员" })).toBeVisible();
  expect(screen.getByRole("table", { name: "待注册邀请" })).toBeVisible();
  expect(screen.getByText("暂无用户账号")).toHaveAttribute("colspan", "5");
});

test("最后登录时间固定显示 UTC+8，跨日和空记录正确展示", async () => {
  const loginTimes = [
    "2026-10-08T16:30:25Z",
    "2026-10-08T10:30:25-05:00",
    null,
    undefined,
  ];
  apiMock.users.mockResolvedValue(
    loginTimes.map((last_seen_at, index) => ({
      id: `user-${index + 1}`,
      display_name: `合成成员 ${index + 1}`,
      email: `member${index + 1}@example.com`,
      active: true,
      last_seen_at,
    })),
  );
  render(<TeamPage notify={vi.fn()} currentUser={{ id: "user-1" }} />);
  const table = await screen.findByRole("table", { name: "团队成员" });
  expect(
    within(table).getByRole("columnheader", { name: "最后登录时间（UTC+8）" }),
  ).toBeVisible();
  const rows = within(table).getAllByRole("row").slice(1);
  ["2026-10-09 00:30:25", "2026-10-08 23:30:25", "--", "--"].forEach(
    (expected, index) => {
      expect(within(rows[index]).getAllByRole("cell")[3]).toHaveTextContent(expected);
    },
  );
});

test("用户数据加载完成前不显示零用户状态", async () => {
  let resolveUsers;
  apiMock.users.mockReturnValue(
    new Promise((resolve) => {
      resolveUsers = resolve;
    }),
  );

  render(
    <TeamPage
      notify={vi.fn()}
      currentUser={{ id: "user-1", display_name: "管理员" }}
    />,
  );

  expect(screen.getByText("正在读取用户与安全设置…")).toBeVisible();
  expect(screen.queryByText("0 个启用账号 · 0 个待注册")).not.toBeInTheDocument();
  expect(screen.queryByText("暂无用户账号")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "邀请用户" })).not.toBeInTheDocument();

  await act(async () => {
    resolveUsers([
      {
        id: "user-1",
        display_name: "管理员",
        email: "admin@example.com",
        active: true,
      },
    ]);
  });

  expect(await screen.findByText("1 个启用账号 · 0 个待注册")).toBeVisible();
  expect(screen.queryByText("正在读取用户与安全设置…")).not.toBeInTheDocument();
});

test("用户数据读取失败时显示重试且不伪装为空列表", async () => {
  const user = userEvent.setup();
  apiMock.users
    .mockRejectedValueOnce(new Error("用户数据暂时不可用"))
    .mockResolvedValueOnce([]);

  render(
    <TeamPage
      notify={vi.fn()}
      currentUser={{ id: "user-1", display_name: "管理员" }}
    />,
  );

  expect(await screen.findByRole("alert")).toHaveTextContent("用户数据暂时不可用");
  expect(screen.queryByText("暂无用户账号")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "重新加载" }));
  expect(await screen.findByText("暂无用户账号")).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("用户目标会高亮并滚入对应成员", async () => {
  const scrollProbe = vi.spyOn(globalThis.HTMLElement.prototype, "scrollIntoView");
  apiMock.users.mockResolvedValue([
    {
      id: "user-1",
      display_name: "管理员",
      email: "admin@example.com",
      active: true,
    },
    {
      id: "user-2",
      display_name: "复核员",
      email: "review@example.com",
      active: true,
    },
  ]);

  render(
    <TeamPage
      notify={vi.fn()}
      currentUser={{ id: "user-1", display_name: "管理员" }}
      focusUserId="user-2"
    />,
  );

  const target = (await screen.findByText("复核员")).closest("tr");
  expect(target).toHaveClass("is-targeted");
  expect(target).toHaveAttribute("aria-current", "true");
  await waitFor(() => expect(scrollProbe).toHaveBeenCalled());
  scrollProbe.mockRestore();
});
