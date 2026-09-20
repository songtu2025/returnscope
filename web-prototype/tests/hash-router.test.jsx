import { afterEach, beforeEach, expect, test } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useEffect } from "react";

import { navigateHash, useHashRoute } from "../src/app/hashRouter";

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

afterEach(() => cleanup());

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
