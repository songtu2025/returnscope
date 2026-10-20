import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api";
import { dashboardApi } from "../src/shared/api/dashboardApi";
import { TaskRuntimePage } from "../src/features/task-runtime/TaskRuntimePage";
import { TaskResultActions } from "../src/features/task-runtime/TaskResultActions";
import { AnalysisDashboardPage } from "../src/features/analysis-dashboards/AnalysisDashboardPage";
import { useHashRoute, parseHash } from "../src/app/hashRouter";
import {
  readDashboardSelection,
  createDashboardSelection,
} from "../src/features/analysis-dashboards/dashboardSelectionStorage";
import { renderWithServerState as render } from "./renderWithServerState";

const actionName = (intent, count = 1) =>
  intent === "insight"
    ? `用本任务结果生成 AI 洞察（${count}）`
    : "用本任务结果创建看板";

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
  ) : route.query.selection_token ? (
    <AnalysisDashboardPage route={route} userId="proof-user" notify={vi.fn()} />
  ) : (
    <p>已进入生成后的页面</p>
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
  vi.spyOn(api, "configs").mockResolvedValue([
    {
      id: "connection",
      models: [
        {
          id: "model",
          active: true,
          validation_status: "validated",
          supported_efforts: ["high"],
        },
      ],
    },
  ]);
  vi.spyOn(api, "modelPreference").mockResolvedValue(null);
  vi.spyOn(dashboardApi, "dashboardPreflight").mockResolvedValue(plan);
  vi.spyOn(dashboardApi, "createAnalysisDashboard").mockResolvedValue({
    id: "new-dashboard",
  });
  vi.spyOn(dashboardApi, "createInsightReportFromResults").mockResolvedValue({
    dashboard: { id: "new-dashboard", version: { version_id: "new-version" } },
    report: { id: "new-report" },
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  sessionStorage.clear();
});

test.each(["dashboard", "insight"])(
  "任务结果 %s 复用预检与确认，键盘进入并返回原任务",
  async (intent) => {
    const user = userEvent.setup();
    const insight = intent === "insight";
    const entryName = actionName(intent);
    const confirmName = insight ? "开始生成" : "确认生成分析看板";
    const submit = insight
      ? dashboardApi.createInsightReportFromResults
      : dashboardApi.createAnalysisDashboard;
    render(<Flow />);
    (await screen.findByRole("button", { name: entryName })).focus();
    await user.keyboard("{Enter}");
    await screen.findByRole("button", { name: confirmName });
    expect(dashboardApi.dashboardPreflight).toHaveBeenCalledWith(
      { result_version_ids: ["result-one"], filters: {} },
      expect.any(Object),
    );
    screen.getAllByText("合成 Listing").forEach((item) => expect(item).toBeVisible());
    if (!insight)
      expect(screen.getByRole("button", { name: confirmName })).toBeDisabled();
    expect(submit).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", {
        name: insight ? "取消" : "返回来源任务",
        exact: true,
      }),
    );
    await screen.findByRole("button", { name: entryName });
    expect(parseHash().query).toMatchObject({
      task_id: "proof-task",
      q: "保留查询",
      status: "finished",
    });
    await user.click(screen.getByRole("button", { name: entryName }));
    if (!insight)
      await user.type(
        await screen.findByRole("textbox", { name: "看板名称" }),
        "合成看板",
      );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: confirmName })).toBeEnabled(),
    );
    await user.click(screen.getByRole("button", { name: confirmName }));
    await waitFor(() => expect(submit).toHaveBeenCalledOnce());
    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        ...(insight
          ? { model_id: "model", reasoning_effort: "high" }
          : { name: "合成看板" }),
        result_version_ids: ["result-one"],
        filters: {},
        plan_hash: plan.plan_hash,
      }),
    );
  },
);

test.each(["dashboard", "insight"])(
  "%s 仅携带有效已发布结果，去重且保留其他结果选择和草稿",
  async (intent) => {
    const token = createDashboardSelection("proof-user", {
      selected: [{ result_version_id: "other" }],
      dashboard_form: { name: "原看板" },
      insight_form: { modelId: "old" },
    });
    const original = readDashboardSelection("proof-user", token);
    render(
      <TaskResultActions
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
    await userEvent.click(
      screen.getByRole("button", {
        name: actionName(intent, 2),
      }),
    );
    const saved = readDashboardSelection(
      "proof-user",
      parseHash().query.selection_token,
    );
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
    expect(saved.intent).toBe(intent);
    expect(readDashboardSelection("proof-user", token)).toEqual(original);
    expect(
      readDashboardSelection("other-user", parseHash().query.selection_token),
    ).toBeNull();
  },
);

test("没有有效结果时不提供入口，执行其他操作期间禁用入口", () => {
  const view = render(
    <TaskResultActions userId="proof-user" task={{ ...task, segments: [] }} />,
  );
  expect(screen.queryByRole("button")).toBeNull();
  view.rerender(<TaskResultActions userId="proof-user" task={task} disabled />);
  for (const button of screen.getAllByRole("button")) expect(button).toBeDisabled();
});

test.each(["dashboard", "insight"])(
  "%s 同Listing多个结果仍进入现有冲突选择，不自动选版本",
  async (intent) => {
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
      await screen.findByRole("button", {
        name: actionName(intent, 2),
      }),
    );
    await waitFor(() => expect(parseHash().query.step).toBe("conflicts"));
    expect(screen.queryByRole("button", { name: "确认生成分析看板" })).toBeNull();
    expect(dashboardApi.createAnalysisDashboard).not.toHaveBeenCalled();
    expect(dashboardApi.createInsightReportFromResults).not.toHaveBeenCalled();
  },
);

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
