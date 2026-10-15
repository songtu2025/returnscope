import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useEffect } from "react";

import { navigateHash, useHashRoute } from "../src/app/hashRouter";
import { NAVIGATION_REQUEST_EVENT } from "../src/app/navigationGuard";

let routeCommitCount = 0;

function RouteHarness() {
  const { route } = useHashRoute();

  useEffect(() => {
    routeCommitCount += 1;
  }, [route]);

  return (
    <>
      <output aria-label="当前标签">{route.query.tab}</output>
      <button onClick={() => navigateHash("settings", { tab: "users" })}>
        用户与安全
      </button>
    </>
  );
}

beforeEach(() => {
  window.location.hash = "#settings?tab=service";
  routeCommitCount = 0;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("内部导航在当前交互内同步路由状态且忽略后续重复事件", () => {
  render(<RouteHarness />);
  expect(screen.getByLabelText("当前标签")).toHaveTextContent("service");

  fireEvent.click(screen.getByRole("button", { name: "用户与安全" }));

  expect(window.location.hash).toBe("#settings?tab=users");
  expect(screen.getByLabelText("当前标签")).toHaveTextContent("users");
  expect(routeCommitCount).toBe(2);

  act(() => window.dispatchEvent(new HashChangeEvent("hashchange")));
  expect(routeCommitCount).toBe(2);
});

test("替换导航和浏览器触发的哈希变化仍能更新路由", () => {
  render(<RouteHarness />);

  act(() => navigateHash("settings", { tab: "audit" }, { replace: true }));
  expect(window.location.hash).toBe("#settings?tab=audit");
  expect(screen.getByLabelText("当前标签")).toHaveTextContent("audit");

  act(() => {
    window.location.hash = "#settings?tab=service";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  expect(screen.getByLabelText("当前标签")).toHaveTextContent("service");
});

test("同地址不创建历史记录，replace保留history其他键和索引", () => {
  window.history.replaceState({ retained: "导航元数据" }, "", "#settings?tab=service");
  render(<RouteHarness />);
  const originalState = { ...window.history.state };
  const push = vi.spyOn(window.history, "pushState");
  act(() => navigateHash("settings", { tab: "service" }));
  expect(push).not.toHaveBeenCalled();
  act(() => navigateHash("settings", { tab: "audit" }, { replace: true }));
  expect(window.history.state).toEqual(originalState);
  expect(screen.getByLabelText("当前标签")).toHaveTextContent("audit");
  act(() => {
    window.dispatchEvent(
      new PopStateEvent("popstate", { state: window.history.state }),
    );
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  expect(routeCommitCount).toBe(2);
});

test("legacy入口规范化仍保留history元数据", () => {
  window.history.replaceState({ retained: "导航元数据" }, "", "#api");
  render(<RouteHarness />);
  expect(window.location.hash).toBe("#settings?tab=api");
  expect(window.history.state.retained).toBe("导航元数据");
});

test("导航被取消时不写URL，恢复动作只提交一次且无重复请求", () => {
  render(<RouteHarness />);
  let resume;
  const request = vi.fn((event) => {
    event.preventDefault();
    resume = event.detail.proceed;
  });
  window.addEventListener(NAVIGATION_REQUEST_EVENT, request);
  try {
    act(() => navigateHash("settings", { tab: "audit" }));
    expect(window.location.hash).toBe("#settings?tab=service");
    expect(screen.getByLabelText("当前标签")).toHaveTextContent("service");
    act(() => resume());
    expect(screen.getByLabelText("当前标签")).toHaveTextContent("audit");
    expect(request).toHaveBeenCalledTimes(1);
  } finally {
    window.removeEventListener(NAVIGATION_REQUEST_EVENT, request);
  }
});
