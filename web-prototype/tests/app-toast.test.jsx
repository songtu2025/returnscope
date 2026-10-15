import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "../src/App";

vi.mock("../src/api", () => ({
  ApiError: class extends Error {},
  api: {
    me: vi.fn().mockResolvedValue({ id: "synthetic-user" }),
    status: vi.fn().mockResolvedValue({ warnings: [] }),
  },
}));
vi.mock("../src/app/AppShell", () => ({
  AppShell: ({ children, overlays }) => (
    <>
      {children}
      {overlays}
    </>
  ),
}));
vi.mock("../src/app/AppPages", () => ({
  AppPages: ({ notify }) => (
    <>
      <button onClick={() => notify("第一条成功")}>第一条</button>
      <button onClick={() => notify("第二条成功")}>第二条</button>
      <button onClick={() => notify("合成错误", "error")}>错误</button>
    </>
  ),
}));

beforeEach(() => {
  vi.useFakeTimers();
  window.location.hash = "#workbench";
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

async function ready() {
  const view = render(<App />);
  await act(async () => {});
  return view;
}

function advance(milliseconds) {
  act(() => vi.advanceTimersByTime(milliseconds));
}

describe("应用操作提示", () => {
  test("成功提示完整停留3200毫秒后自动关闭", async () => {
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "第一条" }));
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
    advance(3199);
    expect(screen.getByText("第一条成功")).toBeVisible();
    advance(1);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  test("新成功提示不被上一条计时器提前关闭", async () => {
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "第一条" }));
    advance(2500);
    fireEvent.click(screen.getByRole("button", { name: "第二条" }));
    advance(700);
    expect(screen.getByText("第二条成功")).toBeVisible();
    advance(2499);
    expect(screen.getByText("第二条成功")).toBeVisible();
    advance(1);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  test("错误替换成功后保留阅读，支持手动关闭", async () => {
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "第一条" }));
    advance(2500);
    fireEvent.click(screen.getByRole("button", { name: "错误" }));
    advance(30000);
    expect(screen.getByRole("alert")).toHaveAttribute("aria-live", "assertive");
    const close = screen.getByRole("button", { name: "关闭错误提示" });
    close.focus();
    expect(close).toHaveFocus();
    vi.useRealTimers();
    await userEvent.setup().keyboard("{Enter}");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  test("成功替换错误后重新使用自动关闭计时", async () => {
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "错误" }));
    fireEvent.click(screen.getByRole("button", { name: "第二条" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    advance(3200);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  test("卸载应用清除尚未执行的提示计时器", async () => {
    const view = await ready();
    fireEvent.click(screen.getByRole("button", { name: "第一条" }));
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    const clear = vi.spyOn(window, "clearTimeout");
    view.unmount();
    expect(clear).toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
    clear.mockRestore();
  });
});
