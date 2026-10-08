import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { AppPages } from "../src/app/AppPages";
import { PageErrorBoundary } from "../src/app/PageErrorBoundary";

vi.mock("../src/app/pageModules", async () => {
  const { lazy } = await import("react");
  const EmptyPage = () => null;
  return {
    WorkbenchPage: lazy(() => Promise.reject(new Error("模拟脚本加载失败"))),
    DataAssetsPage: () => <h1>数据资产</h1>,
    TaskCreatePage: EmptyPage,
    TaskRuntimePage: EmptyPage,
    ClassificationStandardsPage: EmptyPage,
    ClassificationResultsPage: EmptyPage,
    AnalysisDashboardPage: EmptyPage,
    SystemSettingsPage: EmptyPage,
  };
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("页面加载错误恢复", () => {
  test("正常页面直接显示，不出现失败提示", () => {
    render(
      <PageErrorBoundary>
        <h1>正常页面</h1>
      </PageErrorBoundary>,
    );
    expect(screen.getByRole("heading", { name: "正常页面" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  test("脚本加载失败保留导航，提供键盘可达的刷新入口，切换页面可恢复", async () => {
    const caughtError = vi.spyOn(console, "error").mockImplementation(() => {});
    const props = {
      user: { id: "synthetic-user" },
      notify: vi.fn(),
      navigate: vi.fn(),
      refreshSystem: vi.fn(),
    };
    const view = (page) => (
      <>
        <nav aria-label="主导航">导航仍然可用</nav>
        <AppPages {...props} route={{ page, query: {} }} />
      </>
    );
    const { rerender } = render(view("workbench"));

    expect(await screen.findByRole("alert")).toHaveTextContent("页面加载失败");
    expect(screen.getByRole("navigation", { name: "主导航" })).toBeInTheDocument();
    expect(screen.queryByText("模拟脚本加载失败")).not.toBeInTheDocument();
    const refresh = screen.getByRole("button", { name: "刷新页面" });
    await userEvent.tab();
    expect(refresh).toHaveFocus();
    expect(caughtError).toHaveBeenCalled();

    rerender(view("data-assets"));
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "数据资产" })).toBeInTheDocument(),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
