import {
  act,
  cleanup,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { renderWithServerState as render } from "./renderWithServerState";
import { requestNavigation } from "../src/app/navigationGuard";
import { DashboardSettingsEditor } from "../src/features/analysis-dashboards/DashboardSettingsEditor";

const { dashboardApi, api } = vi.hoisted(() => ({
  dashboardApi: {
    analysisDashboard: vi.fn(),
    analysisDashboardSources: vi.fn(),
    dashboardPreflight: vi.fn(),
    updateAnalysisDashboard: vi.fn(),
  },
  api: { classificationResults: vi.fn() },
}));
vi.mock("../src/shared/api/dashboardApi", () => ({ dashboardApi }));
vi.mock("../src/api", () => ({ api }));

const source = (id) => ({ result_version_id: id, store_site: "合成店铺", listing: id });
const dashboard = {
  id: "dashboard-test",
  revision: 1,
  name: "原看板",
  current_version_id: "v1",
  version: {
    filters: {
      quality_status: ["ready"],
      date_from: "2026-10-01",
      date_to: "2026-10-10",
    },
  },
};
const latest = {
  ...dashboard,
  revision: 2,
  name: "同事的名称",
  current_version_id: "v2",
  version: {
    filters: {
      quality_status: ["unusable"],
      date_from: "2026-10-02",
      date_to: "2026-10-11",
    },
  },
};
const conflict = () =>
  Object.assign(new Error("看板已被其他用户更新，请刷新后重试"), { status: 409 });

beforeEach(() => {
  vi.resetAllMocks();
  dashboardApi.analysisDashboard.mockResolvedValue(latest);
  dashboardApi.analysisDashboardSources.mockImplementation(async (_id, version) => [
    source(version === "v1" ? "原来源" : "同事来源"),
  ]);
  dashboardApi.dashboardPreflight.mockResolvedValue({
    plan_hash: "plan",
    conflicts: [],
  });
  dashboardApi.updateAnalysisDashboard
    .mockRejectedValueOnce(conflict())
    .mockResolvedValue({ current_version_id: "v3" });
  api.classificationResults.mockResolvedValue({
    items: [
      {
        version_id: "我的来源",
        store_site: "合成店铺",
        listing: "我的来源",
        version: 1,
      },
    ],
    total: 1,
  });
});
afterEach(cleanup);

async function openEditor() {
  render(
    <DashboardSettingsEditor
      dashboard={dashboard}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "保存修改" })).toBeEnabled(),
  );
}
function change(label, value) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}
async function saveToConflict() {
  fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
  await screen.findByRole("region", { name: "看板配置冲突" });
}
async function readLatest() {
  fireEvent.click(screen.getByRole("button", { name: "读取最新配置" }));
  return screen.findByRole("region", { name: "最新看板配置核对" });
}
function choose(field, label) {
  fireEvent.click(
    within(screen.getByRole("group", { name: `${field}冲突` })).getByLabelText(label),
  );
}

test("409保留五类输入，核对选择后才允许使用新修订号保存", async () => {
  await openEditor();
  change("看板名称", "我的名称");
  change("反馈开始日期", "2026-10-03");
  change("反馈结束日期", "2026-10-12");
  fireEvent.click(screen.getByLabelText("需复核"));
  fireEvent.click(await screen.findByLabelText("合成店铺 · 我的来源 · v1"));
  await saveToConflict();
  expect(screen.getByLabelText("看板名称")).toHaveValue("我的名称");
  expect(screen.getByRole("button", { name: "保存修改" })).toBeDisabled();
  fireEvent.submit(screen.getByLabelText("看板名称").closest("form"));
  expect(dashboardApi.updateAnalysisDashboard).toHaveBeenCalledOnce();
  await readLatest();
  expect(dashboardApi.analysisDashboardSources).toHaveBeenLastCalledWith(
    "dashboard-test",
    "v2",
  );
  expect(screen.getByRole("button", { name: "应用核对结果" })).toBeDisabled();
  choose("看板名称", "最新配置");
  choose("来源结果", "我的输入");
  choose("统计记录范围", "我的输入");
  choose("反馈开始日期", "最新配置");
  choose("反馈结束日期", "我的输入");
  fireEvent.click(screen.getByRole("button", { name: "应用核对结果" }));
  expect(dashboardApi.updateAnalysisDashboard).toHaveBeenCalledOnce();
  expect(screen.getByLabelText("看板名称")).toHaveValue("同事的名称");
  expect(screen.getByText("已选择 2 个来源")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
  await waitFor(() =>
    expect(dashboardApi.updateAnalysisDashboard).toHaveBeenCalledTimes(2),
  );
  expect(dashboardApi.updateAnalysisDashboard.mock.calls[1][1]).toMatchObject({
    expected_revision: 2,
    name: "同事的名称",
    result_version_ids: ["原来源", "我的来源"],
    filters: {
      quality_status: ["ready", "review_required"],
      date_from: "2026-10-02",
      date_to: "2026-10-12",
    },
  });
});

test("单方修改自动合并但必须应用核对结果，不覆盖另一方修改", async () => {
  dashboardApi.analysisDashboard.mockResolvedValue({
    ...latest,
    version: dashboard.version,
  });
  await openEditor();
  change("反馈开始日期", "2026-10-05");
  await saveToConflict();
  const comparison = await readLatest();
  expect(within(comparison).queryByRole("radio")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "保存修改" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "应用核对结果" }));
  expect(screen.getByLabelText("看板名称")).toHaveValue("同事的名称");
  expect(screen.getByLabelText("反馈开始日期")).toHaveValue("2026-10-05");
  expect(screen.getByRole("region", { name: "已选来源" })).toHaveTextContent(
    "同事来源",
  );
  fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
  await waitFor(() =>
    expect(dashboardApi.updateAnalysisDashboard).toHaveBeenCalledTimes(2),
  );
  expect(dashboardApi.updateAnalysisDashboard.mock.calls[1][1]).toMatchObject({
    expected_revision: 2,
    name: "同事的名称",
    result_version_ids: ["同事来源"],
    filters: { date_from: "2026-10-05" },
  });
});

test("最新来源读取失败保留输入和旧修订号，可独立重试", async () => {
  await openEditor();
  change("看板名称", "保留的草稿");
  await saveToConflict();
  dashboardApi.analysisDashboardSources.mockRejectedValueOnce(new Error("合成来源503"));
  fireEvent.click(screen.getByRole("button", { name: "读取最新配置" }));
  await screen.findByText("最新配置读取失败：合成来源503");
  expect(screen.getByLabelText("看板名称")).toHaveValue("保留的草稿");
  expect(
    screen.queryByRole("region", { name: "最新看板配置核对" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "保存修改" })).toBeDisabled();
  const next = vi.fn();
  act(() => expect(requestNavigation(next)).toBe(false));
  expect(screen.getByRole("button", { name: "保存后离开" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
  await readLatest();
  expect(screen.queryByText(/合成来源503/)).not.toBeInTheDocument();
  expect(dashboardApi.updateAnalysisDashboard).toHaveBeenCalledOnce();
});

test("核对期间修改冲突字段会重新要求选择，第二次409重新读取且保留草稿", async () => {
  dashboardApi.updateAnalysisDashboard
    .mockReset()
    .mockRejectedValueOnce(conflict())
    .mockRejectedValueOnce(conflict())
    .mockResolvedValue({ current_version_id: "v4" });
  await openEditor();
  change("看板名称", "我的名称");
  await saveToConflict();
  await readLatest();
  choose("看板名称", "我的输入");
  change("看板名称", "修改后的草稿");
  expect(screen.getByRole("button", { name: "应用核对结果" })).toBeDisabled();
  choose("看板名称", "我的输入");
  fireEvent.click(screen.getByRole("button", { name: "应用核对结果" }));
  await saveToConflict();
  expect(screen.getByLabelText("看板名称")).toHaveValue("修改后的草稿");
  expect(
    screen.queryByRole("region", { name: "最新看板配置核对" }),
  ).not.toBeInTheDocument();
  dashboardApi.analysisDashboard.mockResolvedValue({
    ...latest,
    revision: 3,
    name: "再次更新的名称",
    current_version_id: "v3",
  });
  await readLatest();
  expect(screen.getByRole("button", { name: "应用核对结果" })).toBeDisabled();
  choose("看板名称", "我的输入");
  fireEvent.click(screen.getByRole("button", { name: "应用核对结果" }));
  fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
  await waitFor(() =>
    expect(dashboardApi.updateAnalysisDashboard).toHaveBeenCalledTimes(3),
  );
  expect(
    dashboardApi.updateAnalysisDashboard.mock.calls.map(
      (call) => call[1].expected_revision,
    ),
  ).toEqual([1, 2, 3]);
  expect(dashboardApi.updateAnalysisDashboard.mock.calls[2][1].name).toBe(
    "修改后的草稿",
  );
});
