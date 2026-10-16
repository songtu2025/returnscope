import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithServerState as render } from "./renderWithServerState";
import { useHashRoute } from "../src/app/hashRouter";
import { AnalysisDashboardPage } from "../src/features/analysis-dashboards/AnalysisDashboardPage";
import { changeDeliveryLifecycle } from "../src/shared/api/deliveryApi";

vi.mock("../src/shared/api/deliveryApi", () => ({ changeDeliveryLifecycle: vi.fn() }));

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
  changeDeliveryLifecycle.mockReset();
  read.mockReset().mockImplementation(async ({ page }) => ({
    items: [{ id: `dashboard-${page}`, name: `看板第${page}页`, status: "active" }],
    total: 45,
  }));
  backChanges.current = {};
  setScroll(0);
  vi.spyOn(window, "scrollTo").mockImplementation(({ top }) => setScroll(top));
  window.history.replaceState(null, "", "#analysis-dashboards?q=鞋&status=active");
});

test("恢复成功后真实缓存刷新失败保留成功反馈，重新加载不重复恢复", async () => {
  window.history.replaceState(null, "", "#analysis-dashboards?status=deleted");
  const item = {
    id: "synthetic-deleted",
    name: "合成已删除看板",
    deleted_at: "2026-10-15",
    revision: 4,
  };
  read.mockReset().mockResolvedValue({ items: [item], total: 1 });
  changeDeliveryLifecycle.mockImplementation(async () => {
    read.mockRejectedValue(new Error("合成列表读取失败503"));
    return { ok: true };
  });
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "恢复分析看板" }));
  await screen.findByText("分析看板更新失败，当前显示上一次数据");
  expect(screen.getByText("已恢复分析看板")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "恢复分析看板" }),
  ).not.toBeInTheDocument();
  const previousReads = read.mock.calls.length;
  await userEvent.click(screen.getByRole("button", { name: "刷新数据" }));
  await waitFor(() => expect(read.mock.calls.length).toBeGreaterThan(previousReads));
  expect(changeDeliveryLifecycle).toHaveBeenCalledOnce();
  read.mockResolvedValue({ items: [], total: 0 });
  await userEvent.click(screen.getByRole("button", { name: "重新加载" }));
  await screen.findByText("没有符合条件的看板");
  expect(screen.queryByText("合成已删除看板")).not.toBeInTheDocument();
  expect(changeDeliveryLifecycle).toHaveBeenCalledOnce();
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

test.each([21, 1])("恢复末项后按总数 %s 校正页码且保留筛选", async (total) => {
  const page = total === 21 ? 2 : 1;
  window.history.replaceState(
    null,
    "",
    `#analysis-dashboards?q=合成&status=deleted&page=${page}`,
  );
  let restored = false;
  read.mockImplementation(async ({ page: requestedPage }) => ({
    items: restored
      ? total === 21 && requestedPage === 1
        ? [{ id: "remaining", name: "剩余合成看板", deleted_at: "2026-10-15" }]
        : []
      : [{ id: "last", name: "末项合成看板", deleted_at: "2026-10-15", revision: 1 }],
    total: restored ? total - 1 : total,
  }));
  changeDeliveryLifecycle.mockImplementation(async () => {
    restored = true;
    return { ok: true };
  });
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "恢复分析看板" }));
  await screen.findByText(total === 21 ? "剩余合成看板" : "没有符合条件的看板");
  expect(read).toHaveBeenLastCalledWith(
    { page: 1, page_size: 20, q: "合成", status: "deleted" },
    {},
  );
  const query = new URLSearchParams(window.location.hash.split("?")[1]);
  expect(query.get("q")).toBe("合成");
  expect(query.get("status")).toBe("deleted");
  expect(Number(query.get("page") || 1)).toBe(1);
  expect(changeDeliveryLifecycle).toHaveBeenCalledOnce();
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
