import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithServerState as render } from "./renderWithServerState";
import { useHashRoute } from "../src/app/hashRouter";
import { AnalysisDashboardPage } from "../src/features/analysis-dashboards/AnalysisDashboardPage";

const { read, backChanges } = vi.hoisted(() => ({
  read: vi.fn(),
  backChanges: { current: {} },
}));
vi.mock("../src/shared/api/dashboardApi", () => ({
  dashboardApi: { analysisDashboards: read },
}));
vi.mock("../src/features/analysis-dashboards/DashboardDetail", () => ({
  DashboardDetail: ({ updateRoute }) => (
    <button
      onClick={() =>
        updateRoute({ dashboardId: "", versionId: "", ...backChanges.current })
      }
    >
      返回看板列表
    </button>
  ),
}));

function Harness() {
  const { route } = useHashRoute();
  return (
    <AnalysisDashboardPage route={route} notify={vi.fn()} userId="synthetic-user" />
  );
}
function setScroll(top) {
  Object.defineProperty(window, "scrollY", { configurable: true, value: top });
}
beforeEach(() => {
  read.mockReset().mockImplementation(async ({ page }) => ({
    items: [{ id: `dashboard-${page}`, name: `看板第${page}页`, status: "active" }],
    total: 45,
  }));
  backChanges.current = {};
  setScroll(0);
  vi.spyOn(window, "scrollTo").mockImplementation(({ top }) => setScroll(top));
  window.history.replaceState(null, "", "#analysis-dashboards?q=鞋&status=active");
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  setScroll(0);
});

async function openSecondPage() {
  render(<Harness />);
  await screen.findByText("看板第1页");
  await userEvent.click(screen.getByRole("button", { name: "下一页" }));
  await screen.findByText("看板第2页");
  setScroll(620);
  await userEvent.click(screen.getByRole("button", { name: "查看", exact: true }));
  await screen.findByRole("button", { name: "返回看板列表" });
}

test("真实翻页进入详情保留筛选和页码，返回恢复原行焦点及滚动", async () => {
  await openSecondPage();
  const query = new URLSearchParams(window.location.hash.split("?")[1]);
  expect(query.get("page")).toBe("2");
  expect(query.get("q")).toBe("鞋");
  expect(query.get("status")).toBe("active");
  expect(window.scrollTo).toHaveBeenLastCalledWith({
    top: 0,
    left: 0,
    behavior: "auto",
  });
  await userEvent.click(screen.getByRole("button", { name: "返回看板列表" }));
  await screen.findByText("看板第2页");
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "查看", exact: true })).toHaveFocus(),
  );
  expect(window.scrollTo).toHaveBeenLastCalledWith({
    top: 620,
    left: 0,
    behavior: "auto",
  });
  expect(
    screen.getByRole("navigation", { name: "分页，第 2 页，共 3 页" }),
  ).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "清除筛选" }));
  await screen.findByText("看板第1页");
  await waitFor(() =>
    expect(read).toHaveBeenLastCalledWith(
      { page: 1, page_size: 20, q: "", status: "" },
      {},
    ),
  );
});

test("返回时原行已消失，归顶并聚焦标题而非其他看板", async () => {
  await openSecondPage();
  read.mockResolvedValue({
    items: [{ id: "replacement", name: "其他看板", status: "active" }],
    total: 45,
  });
  await userEvent.click(screen.getByRole("button", { name: "返回看板列表" }));
  await screen.findByText("其他看板");
  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "分析看板" })).toHaveFocus(),
  );
  expect(window.scrollTo).toHaveBeenLastCalledWith({
    top: 0,
    left: 0,
    behavior: "auto",
  });
});

test("返回筛选范围变化不恢复旧坐标和旧行焦点", async () => {
  await openSecondPage();
  backChanges.current = { q: "新范围", page: 1 };
  await userEvent.click(screen.getByRole("button", { name: "返回看板列表" }));
  await screen.findByText("看板第1页");
  await waitFor(() =>
    expect(read).toHaveBeenLastCalledWith(
      { page: 1, page_size: 20, q: "新范围", status: "active" },
      {},
    ),
  );
  expect(screen.getByRole("button", { name: "查看", exact: true })).not.toHaveFocus();
  expect(window.scrollY).toBe(0);
});

test("独立详情入口返回列表不复用其他会话的位置", async () => {
  window.history.replaceState(null, "", "#analysis-dashboards?dashboard=direct&page=2");
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "返回看板列表" }));
  await screen.findByText("看板第2页");
  expect(screen.getByRole("button", { name: "查看", exact: true })).not.toHaveFocus();
  expect(window.scrollY).toBe(0);
});

test("返回刷新失败仍显示原缓存与错误，并恢复原行焦点", async () => {
  await openSecondPage();
  read.mockRejectedValue(new Error("合成连接错误"));
  await userEvent.click(screen.getByRole("button", { name: "返回看板列表" }));
  await screen.findByText("分析看板更新失败，当前显示上一次数据");
  expect(screen.getByText("合成连接错误")).toBeInTheDocument();
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "查看", exact: true })).toHaveFocus(),
  );
  expect(window.scrollY).toBe(620);
});
