import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { preloadPage } from "../src/app/pageModules";
import { Sidebar } from "../src/app/Sidebar";

vi.mock("../src/features/task-runtime/TaskRuntimePage", () => ({
  get TaskRuntimePage() {
    throw new TypeError("Failed to fetch dynamically imported module: /assets/old.js");
  },
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("悬停预加载失败后仍能编辑及聚焦导航，错误不会成为未处理拒绝", async () => {
  const warning = vi.spyOn(console, "warn").mockImplementation(() => {});
  const onNavigate = vi.fn();
  window.location.hash =
    "#classification-results?record_quality_status=review_required";
  const hash = window.location.hash;
  render(
    <>
      <Sidebar page="classification-results" system={null} onNavigate={onNavigate} />
      <label>
        人工观点
        <textarea defaultValue="未保存的人工修正" />
      </label>
    </>,
  );
  const nav = screen.getByRole("button", { name: "分析任务" });
  await userEvent.hover(nav);
  await waitFor(() =>
    expect(warning).toHaveBeenCalledWith(
      "页面预加载失败，将在打开页面时重试。",
      expect.any(TypeError),
    ),
  );
  nav.focus();
  await preloadPage("analysis-tasks");

  await userEvent.type(screen.getByLabelText("人工观点"), "，继续编辑");
  expect(screen.getByLabelText("人工观点")).toHaveValue("未保存的人工修正，继续编辑");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(onNavigate).not.toHaveBeenCalled();
  expect(window.location.hash).toBe(hash);
});

test("没有预加载入口的页面保持可导航", () => {
  expect(preloadPage("unknown-page")).toBeUndefined();
});
