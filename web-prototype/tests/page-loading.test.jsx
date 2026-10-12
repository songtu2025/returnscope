import { apiMock } from "./product-flow-mocks";
import { Suspense, lazy } from "react";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { InlineLoading, PageLoadingState } from "../src/components/SharedUi";
import { PageLoadingScope } from "../src/app/PageLoadingScope";
import { AppPages } from "../src/app/AppPages";
import { renderWithServerState } from "./renderWithServerState";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function advance(time) {
  act(() => vi.advanceTimersByTime(time));
  act(() => vi.advanceTimersByTime(0));
}

test("串行代码与数据加载共用节点，不重复延迟或重启动画", async () => {
  vi.useFakeTimers();
  let resolveModule;
  const DataPage = lazy(
    () =>
      new Promise((resolve) => {
        resolveModule = resolve;
      }),
  );
  const { container, rerender } = render(
    <PageLoadingScope>
      <Suspense fallback={<PageLoadingState label="代码加载" />}>
        <DataPage />
      </Suspense>
    </PageLoadingScope>,
  );
  advance(200);
  const indicator = container.querySelector(".loading-indicator");
  expect(indicator).toBeInTheDocument();
  await act(async () =>
    resolveModule({
      default: () => <InlineLoading scope="page" label="详情加载" />,
    }),
  );
  expect(container.querySelectorAll(".loading-indicator")).toHaveLength(1);
  expect(container.querySelector(".loading-indicator")).toBe(indicator);
  rerender(
    <PageLoadingScope>
      <InlineLoading scope="page" label="列表加载" />
    </PageLoadingScope>,
  );
  expect(container.querySelector(".loading-indicator")).toBe(indicator);
  rerender(
    <PageLoadingScope>
      <p>数据已就绪</p>
    </PageLoadingScope>,
  );
  advance(80);
  expect(container.querySelector(".loading-indicator")).not.toBeInTheDocument();
});

test("交接空档保留已显示节点，但快请求与空闲交接不闪烁", () => {
  vi.useFakeTimers();
  const { container, rerender } = render(
    <PageLoadingScope>
      <InlineLoading scope="page" label="首读" />
    </PageLoadingScope>,
  );
  advance(150);
  rerender(<PageLoadingScope />);
  advance(60);
  expect(container.querySelector(".loading-indicator")).not.toBeInTheDocument();
  rerender(
    <PageLoadingScope>
      <InlineLoading scope="page" label="下阶段" />
    </PageLoadingScope>,
  );
  advance(1);
  const indicator = container.querySelector(".loading-indicator");
  expect(indicator).toBeInTheDocument();
  rerender(<PageLoadingScope />);
  advance(30);
  rerender(
    <PageLoadingScope>
      <InlineLoading scope="page" label="末阶段" />
    </PageLoadingScope>,
  );
  expect(container.querySelector(".loading-indicator")).toBe(indicator);
  rerender(<PageLoadingScope />);
  advance(80);
  expect(container.querySelector(".loading-indicator")).not.toBeInTheDocument();
});

test("并行首读合并，局部刷新和弹窗不占用页面提示，输入焦点保留", () => {
  vi.useFakeTimers();
  const view = (first, second, local = false) => (
    <PageLoadingScope>
      <input aria-label="草稿" defaultValue="保留输入" />
      {first && <InlineLoading scope="page" label="列表" />}
      {second && <InlineLoading scope="page" label="详情" />}
      <InlineLoading compact active={local} label="更新中…" />
    </PageLoadingScope>
  );
  const { container, rerender } = render(view(true, true));
  const input = screen.getByRole("textbox", { name: "草稿" });
  input.focus();
  advance(200);
  expect(container.querySelectorAll(".loading-indicator")).toHaveLength(1);
  rerender(view(false, true));
  expect(container.querySelector(".page-loading-scope")).toHaveAttribute(
    "aria-busy",
    "true",
  );
  rerender(view(false, false, true));
  advance(200);
  expect(
    container.querySelector(".page-loading-slot .loading-indicator"),
  ).not.toBeInTheDocument();
  expect(screen.getByText("更新中…")).toBeVisible();
  expect(document.activeElement).toBe(input);
  expect(input).toHaveValue("保留输入");
});

test("页面切换清理旧提示，失败结束后重试重新延迟", () => {
  vi.useFakeTimers();
  const { container, rerender } = render(
    <PageLoadingScope key="old">
      <InlineLoading scope="page" label="旧页面" />
    </PageLoadingScope>,
  );
  advance(200);
  rerender(
    <PageLoadingScope key="new">
      <p role="alert">读取失败</p>
    </PageLoadingScope>,
  );
  advance(80);
  expect(container.querySelector(".loading-indicator")).not.toBeInTheDocument();
  rerender(
    <PageLoadingScope key="new">
      <InlineLoading scope="page" label="重试" />
    </PageLoadingScope>,
  );
  advance(199);
  expect(container.querySelector(".loading-indicator")).not.toBeInTheDocument();
  advance(1);
  expect(container.querySelectorAll(".loading-indicator")).toHaveLength(1);
});

test("实际 AppPages 产品列表、详情与行数据首读始终共用提示", async () => {
  let resolveList, resolveDetail, resolveRows;
  apiMock.datasets.mockImplementation(
    () =>
      new Promise((resolve) => {
        resolveList = resolve;
      }),
  );
  apiMock.dataset.mockImplementation(
    () =>
      new Promise((resolve) => {
        resolveDetail = resolve;
      }),
  );
  apiMock.datasetRows.mockImplementation(
    () =>
      new Promise((resolve) => {
        resolveRows = resolve;
      }),
  );
  const { container } = renderWithServerState(
    <AppPages
      route={{ page: "data-assets", query: {} }}
      user={{ id: "qa" }}
      notify={vi.fn()}
      navigate={vi.fn()}
      refreshSystem={vi.fn()}
    />,
  );
  await screen.findByText("正在读取页面…");
  const indicator = container.querySelector(".loading-indicator");
  const product = {
    id: "synthetic",
    kind: "products",
    current_version: 1,
    version_id: "synthetic-v1",
    name: "合成产品",
    row_count: 0,
    column_count: 0,
    schema: [],
    audit: [],
  };
  await waitFor(() => expect(apiMock.datasets).toHaveBeenCalled(), { timeout: 5000 });
  await act(async () => resolveList([product]));
  expect(container.querySelector(".loading-indicator")).toBe(indicator);
  await act(async () => resolveDetail(product));
  expect(container.querySelector(".loading-indicator")).toBe(indicator);
  await act(async () =>
    resolveRows({ records: [], total: 0, facets: { stores: [], categories: [] } }),
  );
  await waitFor(() =>
    expect(container.querySelector(".page-loading-scope")).toHaveAttribute(
      "aria-busy",
      "false",
    ),
  );
  await act(async () => new Promise((resolve) => setTimeout(resolve, 100)));
  expect(container.querySelector(".loading-indicator")).not.toBeInTheDocument();
});
