import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api";
import { dashboardApi } from "../src/shared/api/dashboardApi";
import { TaskRuntimePage } from "../src/features/task-runtime/TaskRuntimePage";
import { TaskResultDashboardAction } from "../src/features/task-runtime/TaskResultDashboardAction";
import { AnalysisDashboardPage } from "../src/features/analysis-dashboards/AnalysisDashboardPage";
import { useHashRoute, parseHash } from "../src/app/hashRouter";
import {
  readDashboardSelection,
  createDashboardSelection,
} from "../src/features/analysis-dashboards/dashboardSelectionStorage";
import { renderWithServerState as render } from "./renderWithServerState";

const base = {
  id: "segment-one",
  segment_key: "one",
  agent_key: "footwear",
  agent_family: "合成品类",
  scope: { store: "合成店铺", listing: "合成 Listing" },
  status: "completed",
  result_version_id: "result-one",
  result_publish_status: "published",
  result_version: 3,
  result_quality_status: "needs_review",
  record_count: 10,
  unique_comments: 5,
  progress_current: 5,
  progress_total: 5,
  variants: [],
};
const task = {
  id: "proof-task",
  title: "合成任务",
  status: "completed",
  revision: 1,
  owner_name: "合成用户",
  created_at: "2026-10-19",
  segments: [base],
};
const plan = {
  plan_hash: "authoritative-plan",
  ready: true,
  conflicts: [],
  blockers: [],
  warnings: [],
  sources: [
    {
      result_version_id: "result-one",
      result_version_no: 3,
      store_site: "合成店铺",
      listing: "合成 Listing",
      record_count: 6,
    },
  ],
  summary: {
    listing_count: 1,
    record_count: 6,
    total_record_count: 10,
    pending_review_record_count: 4,
  },
};
function Flow() {
  const { route } = useHashRoute();
  return route.page === "analysis-tasks" ? (
    <TaskRuntimePage
      route={route}
      userId="proof-user"
      notify={vi.fn()}
      onNavigate={vi.fn()}
      onChanged={vi.fn()}
    />
  ) : (
    <AnalysisDashboardPage route={route} userId="proof-user" notify={vi.fn()} />
  );
}
beforeEach(() => {
  sessionStorage.clear();
  window.history.replaceState(
    {},
    "",
    "/#analysis-tasks?task_id=proof-task&q=保留查询&status=finished",
  );
  vi.spyOn(api, "tasks").mockResolvedValue([]);
  vi.spyOn(api, "task").mockResolvedValue(task);
  vi.spyOn(dashboardApi, "dashboardPreflight").mockResolvedValue(plan);
  vi.spyOn(dashboardApi, "createAnalysisDashboard").mockResolvedValue({
    id: "new-dashboard",
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  sessionStorage.clear();
});

test("真实任务入口复用看板预检，核对范围后才允许创建，并可返回原任务", async () => {
  const user = userEvent.setup();
  render(<Flow />);
  await user.click(await screen.findByRole("button", { name: "用本任务结果创建看板" }));
  await screen.findByRole("button", { name: "确认生成分析看板" });
  expect(dashboardApi.dashboardPreflight).toHaveBeenCalledWith(
    { result_version_ids: ["result-one"], filters: {} },
    expect.any(Object),
  );
  expect(screen.getByText("合成 Listing")).toBeVisible();
  expect(screen.getByRole("button", { name: "确认生成分析看板" })).toBeDisabled();
  expect(dashboardApi.createAnalysisDashboard).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "返回来源任务" }));
  await screen.findByRole("button", { name: "用本任务结果创建看板" });
  expect(parseHash().query).toMatchObject({
    task_id: "proof-task",
    q: "保留查询",
    status: "finished",
  });
  await user.click(screen.getByRole("button", { name: "用本任务结果创建看板" }));
  await user.type(await screen.findByRole("textbox", { name: "看板名称" }), "合成看板");
  await user.click(screen.getByRole("button", { name: "确认生成分析看板" }));
  await waitFor(() =>
    expect(dashboardApi.createAnalysisDashboard).toHaveBeenCalledOnce(),
  );
  expect(dashboardApi.createAnalysisDashboard).toHaveBeenCalledWith(
    expect.objectContaining({
      name: "合成看板",
      result_version_ids: ["result-one"],
      filters: {},
      plan_hash: plan.plan_hash,
    }),
  );
});

test("仅携带有效已发布结果，结果ID去重，排除移除、删除、未发布及旧文件", async () => {
  render(
    <TaskResultDashboardAction
      userId="proof-user"
      task={{
        ...task,
        segments: [
          base,
          { ...base, id: "duplicate" },
          { ...base, result_version_id: "removed", deleted_at: "2026-10-19" },
          { ...base, result_version_id: "deleted", result_deleted_at: "2026-10-19" },
          {
            ...base,
            result_version_id: "publishing",
            result_publish_status: "pending",
          },
          {
            ...base,
            result_version_id: "",
            result_publish_status: "",
            result_file_path: "legacy.xlsx",
          },
          { ...base, result_version_id: "result-two", result_version: 4 },
        ],
      }}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "用本任务结果创建看板" }));
  const saved = readDashboardSelection("proof-user", parseHash().query.selection_token);
  expect(saved.selected.map((item) => item.result_version_id)).toEqual([
    "result-one",
    "result-two",
  ]);
  expect(saved.selected[0]).toMatchObject({
    result_version_no: 3,
    quality_status: "needs_review",
  });
  expect(saved.filters).toBeUndefined();
  expect(saved.task_return).toContain("task_id=proof-task");
});

test("没有有效结果时不提供入口，执行其他操作期间禁用入口", () => {
  const view = render(
    <TaskResultDashboardAction userId="proof-user" task={{ ...task, segments: [] }} />,
  );
  expect(screen.queryByRole("button")).toBeNull();
  view.rerender(<TaskResultDashboardAction userId="proof-user" task={task} disabled />);
  expect(screen.getByRole("button")).toBeDisabled();
});

test("同Listing多个结果仍进入现有冲突选择，不自动替用户选版本", async () => {
  vi.mocked(dashboardApi.dashboardPreflight).mockResolvedValue({
    ...plan,
    ready: false,
    conflicts: [
      {
        conflict_id: "same-listing",
        store_site: "合成店铺",
        listing: "合成 Listing",
        result_version_ids: ["result-one", "result-two"],
      },
    ],
  });
  vi.mocked(api.task).mockResolvedValue({
    ...task,
    segments: [
      base,
      { ...base, id: "two", segment_key: "two", result_version_id: "result-two" },
    ],
  });
  render(<Flow />);
  await userEvent.click(
    await screen.findByRole("button", { name: "用本任务结果创建看板" }),
  );
  await waitFor(() => expect(parseHash().query.step).toBe("conflicts"));
  expect(screen.queryByRole("button", { name: "确认生成分析看板" })).toBeNull();
  expect(dashboardApi.createAnalysisDashboard).not.toHaveBeenCalled();
});

test("非法任务返回地址退回既有结果池流程", async () => {
  const token = createDashboardSelection("proof-user", {
    selected: [{ result_version_id: "result-one" }],
    task_return: "#settings?action=delete",
  });
  window.history.replaceState(
    {},
    "",
    `/#analysis-dashboards?selection_token=${token}&step=check`,
  );
  render(<Flow />);
  await screen.findByRole("button", { name: "返回选择分类结果" });
  expect(screen.queryByRole("button", { name: "返回来源任务" })).toBeNull();
});
