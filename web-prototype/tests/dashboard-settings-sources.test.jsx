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
    analysisDashboardSources: vi.fn(),
    dashboardPreflight: vi.fn(),
    updateAnalysisDashboard: vi.fn(),
  },
  api: { classificationResults: vi.fn() },
}));
vi.mock("../src/shared/api/dashboardApi", () => ({ dashboardApi }));
vi.mock("../src/api", () => ({ api }));

const dashboard = {
  id: "dashboard-test",
  revision: 1,
  name: "合成看板",
  current_version_id: "dashboard-v1",
  version: { filters: { quality_status: ["ready"], date_from: "2026-10-01" } },
};
const originalSource = {
  result_version_id: "result-original",
  store_site: "合成店铺",
  listing: "原来源",
};

beforeEach(() => {
  vi.resetAllMocks();
  dashboardApi.analysisDashboardSources.mockResolvedValue([originalSource]);
  dashboardApi.dashboardPreflight.mockResolvedValue({
    plan_hash: "plan",
    conflicts: [],
  });
  dashboardApi.updateAnalysisDashboard.mockResolvedValue({
    current_version_id: "dashboard-v2",
  });
  api.classificationResults.mockImplementation(async ({ page }) => ({
    items: [
      {
        version_id: `result-${page}`,
        store_site: "合成店铺",
        listing: `来源${page}`,
        version: 1,
      },
    ],
    total: 21,
  }));
});
afterEach(cleanup);

function openEditor() {
  render(
    <DashboardSettingsEditor
      dashboard={dashboard}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
}

test("跨页选中来源均保留在摘要，可移除其他页来源且提交与摘要一致", async () => {
  openEditor();
  const first = await screen.findByLabelText("合成店铺 · 来源1 · v1");
  await waitFor(() => expect(first).toBeEnabled());
  fireEvent.click(first);
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  fireEvent.click(await screen.findByLabelText("合成店铺 · 来源2 · v1"));
  const selected = screen.getByRole("region", { name: "已选来源" });
  expect(within(selected).getByText("已选择 3 个来源")).toBeInTheDocument();
  expect(within(selected).getAllByRole("button")).toHaveLength(3);
  fireEvent.click(
    within(selected).getByRole("button", { name: "移除来源 合成店铺 · 来源1" }),
  );
  expect(within(selected).getByText("已选择 2 个来源")).toBeInTheDocument();
  expect(within(selected).queryByText("合成店铺 · 来源1")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "上一页" }));
  await waitFor(() =>
    expect(screen.getByLabelText("合成店铺 · 来源1 · v1")).not.toBeChecked(),
  );
  fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
  await waitFor(() =>
    expect(dashboardApi.updateAnalysisDashboard).toHaveBeenCalledOnce(),
  );
  expect(
    dashboardApi.updateAnalysisDashboard.mock.calls[0][1].result_version_ids,
  ).toEqual(["result-original", "result-2"]);
});

test("已选摘要补全不改变保存基线，新选择仍受离页保护", async () => {
  openEditor();
  const first = await screen.findByLabelText("合成店铺 · 来源1 · v1");
  await waitFor(() => expect(first).toBeEnabled());
  const proceed = vi.fn();
  expect(requestNavigation(proceed)).toBe(true);
  fireEvent.click(first);
  expect(
    screen.getByRole("button", { name: "移除来源 合成店铺 · 来源1" }),
  ).toBeInTheDocument();
  act(() => expect(requestNavigation(proceed)).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
  fireEvent.click(screen.getByRole("button", { name: "移除来源 合成店铺 · 来源1" }));
  expect(requestNavigation(proceed)).toBe(true);
});

test("原绑定来源读取503后独立重试保留名称和范围，恢复后仍按原值判断未保存", async () => {
  dashboardApi.analysisDashboardSources.mockRejectedValueOnce(new Error("合成来源503"));
  openEditor();
  await screen.findByText(/已绑定来源读取失败：合成来源503/);
  const choice = await screen.findByLabelText("合成店铺 · 来源1 · v1");
  expect(choice).toBeDisabled();
  expect(screen.getByRole("button", { name: "保存修改" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("看板名称"), {
    target: { value: "保留的新名称" },
  });
  fireEvent.change(screen.getByLabelText("反馈开始日期"), {
    target: { value: "2026-10-10" },
  });
  fireEvent.click(screen.getByLabelText("需复核"));
  fireEvent.click(screen.getByRole("button", { name: "重试已绑定来源" }));
  await waitFor(() => expect(choice).toBeEnabled());
  expect(screen.queryByText(/合成来源503/)).not.toBeInTheDocument();
  expect(screen.getByLabelText("看板名称")).toHaveValue("保留的新名称");
  expect(screen.getByLabelText("反馈开始日期")).toHaveValue("2026-10-10");
  expect(screen.getByLabelText("需复核")).toBeChecked();
  expect(screen.getByText("已选择 1 个来源")).toBeInTheDocument();
  const proceed = vi.fn();
  act(() => expect(requestNavigation(proceed)).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
  fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
  await waitFor(() =>
    expect(dashboardApi.updateAnalysisDashboard).toHaveBeenCalledOnce(),
  );
  expect(dashboardApi.analysisDashboardSources).toHaveBeenCalledTimes(2);
  expect(dashboardApi.updateAnalysisDashboard.mock.calls[0][1]).toMatchObject({
    name: "保留的新名称",
    result_version_ids: ["result-original"],
    filters: { date_from: "2026-10-10", quality_status: ["ready", "review_required"] },
  });
});

test("原绑定来源重试再次失败仍可重试且没有清空草稿或提交", async () => {
  dashboardApi.analysisDashboardSources
    .mockRejectedValueOnce(new Error("首次503"))
    .mockRejectedValueOnce(new Error("再次503"));
  openEditor();
  await screen.findByText(/首次503/);
  fireEvent.change(screen.getByLabelText("看板名称"), {
    target: { value: "保留草稿" },
  });
  fireEvent.click(screen.getByRole("button", { name: "重试已绑定来源" }));
  await screen.findByText(/再次503/);
  expect(screen.getByLabelText("看板名称")).toHaveValue("保留草稿");
  expect(screen.getByRole("button", { name: "重试已绑定来源" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "保存修改" })).toBeDisabled();
  expect(dashboardApi.dashboardPreflight).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "重试已绑定来源" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "保存修改" })).toBeEnabled(),
  );
  expect(screen.getByLabelText("看板名称")).toHaveValue("保留草稿");
});
