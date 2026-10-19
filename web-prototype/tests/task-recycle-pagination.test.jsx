import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { renderWithServerState as render } from "./renderWithServerState";
import { mocks, item } from "./task-recycle-test-state";
import { TaskRecyclePage } from "../src/features/task-runtime/TaskRecyclePage";
const topPager = () => within(screen.getByRole("group", { name: "回收站顶部分页" }));

test("搜索显示全量与匹配数量，清除和空态重置回到全部记录", async () => {
  mocks.request.mockImplementation(async (url) => {
    const query = new URL(url, "http://localhost").searchParams.get("q");
    return {
      items: query === "无匹配" ? [] : [item],
      total: query ? (query === "无匹配" ? 0 : 2) : 23,
    };
  });
  render(<TaskRecyclePage notify={vi.fn()} />);
  await screen.findByText("共 23 条 · 第 1 页");
  const search = screen.getByRole("textbox", { name: "搜索回收站" });
  await userEvent.type(search, "SYNTHETIC{Enter}");
  await screen.findByText("共 23 条 · 第 1 页 · 匹配 2 条 · 当前搜索：SYNTHETIC");
  await userEvent.click(screen.getByRole("button", { name: "清除搜索", exact: true }));
  expect(search).toHaveValue("");
  await userEvent.type(search, "无匹配{Enter}");
  await screen.findByText("没有匹配的移除记录");
  await userEvent.click(screen.getByRole("button", { name: "清除搜索，查看全部" }));
  expect(search).toHaveValue("");
  expect(await screen.findByText("SYNTHETIC")).toBeVisible();
});

test("总数读取失败不伪装成零条，保留匹配结果并可刷新重试", async () => {
  let failCount = true;
  mocks.request.mockImplementation(async (url) => {
    const params = new URL(url, "http://localhost").searchParams;
    if (params.get("page_size") === "1" && failCount) throw new Error("合成计数失败");
    return { items: [item], total: params.get("q") ? 1 : 23 };
  });
  render(<TaskRecyclePage notify={vi.fn()} />);
  await screen.findByText("SYNTHETIC");
  await userEvent.type(
    screen.getByRole("textbox", { name: "搜索回收站" }),
    "SYNTHETIC{Enter}",
  );
  await screen.findByText(/总数暂不可用.*匹配 1 条/);
  expect(screen.getByText("SYNTHETIC", { selector: "b" })).toBeVisible();
  failCount = false;
  await userEvent.click(screen.getByRole("button", { name: "刷新回收站" }));
  await screen.findByText(/共 23 条.*匹配 1 条/);
});

test("顶底分页共用页码并支持直接跳页", async () => {
  mocks.request.mockResolvedValue({ items: [item], total: 65 });
  render(<TaskRecyclePage notify={vi.fn()} />);
  await screen.findByText("SYNTHETIC");
  const jumper = topPager().getByRole("textbox");
  await userEvent.type(jumper, "3");
  fireEvent.keyUp(jumper, { key: "Enter", keyCode: 13 });
  await waitFor(() =>
    expect(
      screen.getAllByRole("navigation", { name: "分页，第 3 页，共 4 页" }),
    ).toHaveLength(2),
  );
  expect(mocks.request).toHaveBeenCalledWith("/api/tasks/recycle?page=3&page_size=20");
  const bottom = within(screen.getByRole("group", { name: "回收站底部分页" }));
  await userEvent.click(bottom.getByRole("button", { name: "上一页" }));
  await waitFor(() =>
    expect(topPager().getByRole("navigation")).toHaveAccessibleName(
      "分页，第 2 页，共 4 页",
    ),
  );
});

test.each([50, 100])("每页数量 %s 使用服务端分页并回到第一页", async (size) => {
  mocks.request.mockResolvedValue({ items: [item], total: 101 });
  render(<TaskRecyclePage notify={vi.fn()} />);
  await screen.findByText("SYNTHETIC");
  await userEvent.click(topPager().getByRole("button", { name: "下一页" }));
  await userEvent.click(topPager().getByRole("combobox", { name: "每页数量" }));
  await userEvent.click(await screen.findByRole("option", { name: `${size} 条/页` }));
  await waitFor(() =>
    expect(mocks.request).toHaveBeenCalledWith(
      `/api/tasks/recycle?page=1&page_size=${size}`,
    ),
  );
  expect(topPager().getByRole("navigation")).toHaveAccessibleName(
    `分页，第 1 页，共 ${Math.ceil(101 / size)} 页`,
  );
});

test("第二页最后一项恢复后自动回落第一页，重复操作不被旧busy锁住", async () => {
  mocks.request.mockImplementation(async (url) => {
    if (url.includes("page=2"))
      return { items: [item], total: mocks.control.mock.calls.length ? 20 : 21 };
    return {
      items: Array.from({ length: 20 }, (_, i) => ({
        ...item,
        id: `first-${i}`,
        scope: { listing: `FIRST-${i}` },
      })),
      total: mocks.control.mock.calls.length ? 20 : 21,
    };
  });
  render(<TaskRecyclePage notify={vi.fn()} />);
  await screen.findByText("FIRST-0");
  await userEvent.click(topPager().getByRole("button", { name: "下一页" }));
  await screen.findByText("SYNTHETIC");
  await userEvent.click(screen.getByRole("button", { name: /^恢复 / }));
  await waitFor(() => expect(screen.getByText("共 20 条 · 第 1 页")).toBeVisible());
  expect(await screen.findByText("FIRST-0")).toBeVisible();
  expect(screen.getAllByRole("button", { name: /^恢复 / })[0]).toBeEnabled();
});

test("恢复期间保留搜索输入但锁定提交和分页，结束后可以操作", async () => {
  let finish;
  mocks.control.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  mocks.request.mockResolvedValue({ items: [item], total: 41 });
  render(<TaskRecyclePage notify={vi.fn()} />);
  await screen.findByText("SYNTHETIC");
  await userEvent.click(topPager().getByRole("button", { name: "下一页" }));
  await screen.findByText("共 41 条 · 第 2 页");
  await userEvent.click(screen.getByRole("button", { name: /^恢复 / }));
  const input = screen.getByRole("textbox", { name: "搜索回收站" });
  await userEvent.type(input, "新范围{Enter}");
  fireEvent.submit(input.closest("form"));
  expect(input).toHaveValue("新范围");
  for (const name of ["搜索", "上一页", "下一页"])
    expect(
      (name === "搜索" ? screen : topPager()).getByRole("button", {
        name,
        exact: true,
      }),
    ).toBeDisabled();
  expect(screen.getByText("共 41 条 · 第 2 页")).toBeVisible();
  expect(mocks.request).toHaveBeenCalledTimes(2);
  await act(async () => finish({}));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "搜索", exact: true })).toBeEnabled(),
  );
  await userEvent.click(topPager().getByRole("button", { name: "上一页" }));
  await screen.findByText("共 41 条 · 第 1 页");
  await userEvent.click(topPager().getByRole("button", { name: "下一页" }));
  await screen.findByText("共 41 条 · 第 2 页");
  await userEvent.click(screen.getByRole("button", { name: "搜索", exact: true }));
  await waitFor(() =>
    expect(mocks.request).toHaveBeenCalledWith(
      `/api/tasks/recycle?q=${encodeURIComponent("新范围")}&page=1&page_size=20`,
    ),
  );
});
