import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api";
import { dashboardApi } from "../src/shared/api/dashboardApi";
import { ClassificationResultsPage } from "../src/pages/ClassificationResultsPage";
import { AnalysisDashboardPage } from "../src/features/analysis-dashboards/AnalysisDashboardPage";
import { ResultPoolContent } from "../src/features/classification-results/ResultPoolContent";
import { classificationResultRouteState } from "../src/features/classification-results/classificationResultRoute";
import { useHashRoute, parseHash, buildHash } from "../src/app/hashRouter";
import {
  createDashboardSelection,
  readDashboardSelection,
  selectionItem,
} from "../src/features/analysis-dashboards/dashboardSelectionStorage";
import { renderWithServerState as render } from "./renderWithServerState";

const item = (id, fields = {}) => ({
  version_id: id,
  version: 1,
  listing: id,
  store_site: "合成店铺",
  publish_status: "published",
  quality_status: "ready",
  record_count: 5,
  unit_count: 3,
  published_at: "2026-10-19",
  ...fields,
});
const first = [
  item("alpha"),
  item("beta", { quality_status: "needs_review" }),
  item("pending", { publish_status: "pending" }),
  item("deleted", { deleted_at: "2026-10-19" }),
];
const second = [item("gamma"), item("delta")];
const selected = () =>
  readDashboardSelection("proof-user", parseHash().query.selection_token);
function Flow() {
  const { route } = useHashRoute();
  return route.page === "analysis-dashboards" ? (
    <AnalysisDashboardPage route={route} userId="proof-user" notify={vi.fn()} />
  ) : (
    <ClassificationResultsPage route={route} userId="proof-user" notify={vi.fn()} />
  );
}
beforeEach(() => {
  sessionStorage.clear();
  window.history.replaceState({}, "", "/#classification-results");
  vi.spyOn(api, "classificationResults").mockImplementation(async (filters) => ({
    items: filters.q === "only-beta" ? [first[1]] : filters.page === 2 ? second : first,
    total: filters.q === "only-beta" ? 1 : 25,
    page: filters.page,
    page_size: 20,
  }));
  vi.spyOn(api, "classificationResultRecordGroups");
  vi.spyOn(dashboardApi, "dashboardPreflight").mockResolvedValue({
    plan_hash: "plan",
    ready: true,
    conflicts: [],
    blockers: [],
    summary: { record_count: 10 },
  });
  vi.spyOn(dashboardApi, "createAnalysisDashboard");
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  sessionStorage.clear();
});

test("键盘一次选中本页全部合格结果，沿用发布规则而非仅选ready", async () => {
  render(<Flow />);
  const all = await screen.findByRole("checkbox", { name: "选择当前页可选结果" });
  expect(screen.getByText("选择当前页 2 个可选结果")).toBeVisible();
  all.focus();
  await userEvent.keyboard(" ");
  expect(all).toBeChecked();
  expect(selected().selected.map((value) => value.result_version_id)).toEqual([
    "alpha",
    "beta",
  ]);
  expect(screen.getByText("当前页已选 2 个")).toBeVisible();
  expect(api.classificationResultRecordGroups).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "新建分析看板" }));
  await screen.findByRole("button", { name: "确认生成分析看板" });
  expect(dashboardApi.dashboardPreflight).toHaveBeenCalledWith(
    { result_version_ids: ["alpha", "beta"], filters: {} },
    expect.any(Object),
  );
  expect(dashboardApi.createAnalysisDashboard).not.toHaveBeenCalled();
});

test("逐项与批量共用选择，半选补齐，全选后取消本页", async () => {
  render(<Flow />);
  const all = await screen.findByRole("checkbox", { name: "选择当前页可选结果" });
  await userEvent.click(screen.getByRole("checkbox", { name: /^选择 alpha 结果/ }));
  expect(all).toBePartiallyChecked();
  await userEvent.click(all);
  expect(all).toBeChecked();
  await userEvent.click(screen.getByRole("checkbox", { name: /^选择 beta 结果/ }));
  expect(all).toBePartiallyChecked();
  await userEvent.click(all);
  expect(selected().selected).toHaveLength(2);
  await userEvent.click(all);
  expect(selected().selected).toEqual([]);
  expect(screen.getByRole("button", { name: "新建分析看板" })).toBeDisabled();
});

test("只改变当前页，跨页选择及取消不影响其他页", async () => {
  render(<Flow />);
  await userEvent.click(
    await screen.findByRole("checkbox", { name: "选择当前页可选结果" }),
  );
  await userEvent.click(screen.getByRole("button", { name: "下一页" }));
  await screen.findByText("选择当前页 2 个可选结果");
  await waitFor(() =>
    expect(screen.getByText("gamma", { selector: "button" })).toBeVisible(),
  );
  const all = screen.getByRole("checkbox", { name: "选择当前页可选结果" });
  await userEvent.click(all);
  expect(selected().selected.map((value) => value.result_version_id)).toEqual([
    "alpha",
    "beta",
    "gamma",
    "delta",
  ]);
  await userEvent.click(all);
  expect(selected().selected.map((value) => value.result_version_id)).toEqual([
    "alpha",
    "beta",
  ]);
  await userEvent.click(screen.getByRole("button", { name: "上一页" }));
  await waitFor(() =>
    expect(screen.getByRole("checkbox", { name: "选择当前页可选结果" })).toBeChecked(),
  );
});

test("保留筛选外结果及创建草稿，选择变化清除旧冲突决议", async () => {
  const token = createDashboardSelection("proof-user", {
    selected: [selectionItem(item("outside"))],
    resolved_result_version_ids: ["old-choice"],
    dashboard_form: { name: "已填看板" },
    insight_form: { modelId: "model", effort: "high" },
    task_return: "#analysis-tasks?task_id=old-source",
  });
  window.history.replaceState(
    {},
    "",
    "/" +
      buildHash("classification-results", { selection_token: token, q: "only-beta" }),
  );
  render(<Flow />);
  await userEvent.click(
    await screen.findByRole("checkbox", { name: "选择当前页可选结果" }),
  );
  expect(selected()).toMatchObject({
    resolved_result_version_ids: [],
    dashboard_form: { name: "已填看板" },
    insight_form: { modelId: "model", effort: "high" },
  });
  await userEvent.click(screen.getByRole("checkbox", { name: "选择当前页可选结果" }));
  expect(selected().selected.map((value) => value.result_version_id)).toEqual([
    "outside",
  ]);
  await userEvent.click(screen.getByRole("button", { name: "新建分析看板" }));
  expect(await screen.findByRole("textbox", { name: "看板名称" })).toHaveValue(
    "已填看板",
  );
  expect(readDashboardSelection("proof-user", token).task_return).toBeUndefined();
  expect(screen.getByRole("button", { name: "返回选择分类结果" })).toBeVisible();
});

test.each([
  { loading: true, error: "" },
  { loading: false, error: "读取失败" },
])("加载或读取失败时禁用批量选择，不使用旧页范围 %s", async (state) => {
  const toggleSelections = vi.fn();
  render(
    <ResultPoolContent
      {...state}
      route={classificationResultRouteState({})}
      data={{ items: first, total: 25 }}
      selectedIds={new Set(["alpha"])}
      toggleSelections={toggleSelections}
      toggleSelection={vi.fn()}
      updateRoute={vi.fn()}
      load={vi.fn()}
    />,
  );
  const all = screen.getByRole("checkbox", { name: "选择当前页可选结果" });
  expect(all).toBeDisabled();
  expect(screen.queryByText("选择当前页 2 个可选结果")).toBeNull();
  all.focus();
  await userEvent.keyboard(" ");
  expect(toggleSelections).not.toHaveBeenCalled();
});

test("同Listing的多个版本全部保留，冲突仍交给原确认流程", async () => {
  vi.mocked(api.classificationResults).mockResolvedValue({
    items: first.slice(0, 2).map((value) => ({ ...value, listing: "同一 Listing" })),
    total: 2,
    page: 1,
    page_size: 20,
  });
  vi.mocked(dashboardApi.dashboardPreflight).mockResolvedValue({
    plan_hash: "conflict-plan",
    ready: false,
    blockers: [],
    conflicts: [
      {
        conflict_id: "same",
        store_site: "合成店铺",
        listing: "同一 Listing",
        result_version_ids: ["alpha", "beta"],
      },
    ],
    summary: {},
  });
  render(<Flow />);
  await userEvent.click(
    await screen.findByRole("checkbox", { name: "选择当前页可选结果" }),
  );
  expect(selected().selected.map((value) => value.result_version_id)).toEqual([
    "alpha",
    "beta",
  ]);
  await userEvent.click(screen.getByRole("button", { name: "新建分析看板" }));
  await waitFor(() => expect(parseHash().query.step).toBe("conflicts"));
  expect(screen.queryByRole("button", { name: "确认生成分析看板" })).toBeNull();
  expect(dashboardApi.createAnalysisDashboard).not.toHaveBeenCalled();
});

test("本页没有合格结果时禁用全选，不增加可选资格", async () => {
  vi.mocked(api.classificationResults).mockResolvedValue({
    items: first.slice(2),
    total: 2,
    page: 1,
    page_size: 20,
  });
  render(<Flow />);
  expect(
    await screen.findByRole("checkbox", { name: "选择当前页可选结果" }),
  ).toBeDisabled();
  expect(screen.getByText("选择当前页 0 个可选结果")).toBeVisible();
});
