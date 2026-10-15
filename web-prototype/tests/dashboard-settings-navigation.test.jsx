import { useState } from "react";
import { act, cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { renderWithServerState as render } from "./renderWithServerState";
import { navigateHash, useHashRoute } from "../src/app/hashRouter";
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
  version: { filters: { quality_status: ["ready"] } },
};
const sources = [
  { result_version_id: "result-a", store_site: "合成店铺", listing: "A" },
];

function Harness() {
  const { route } = useHashRoute();
  const [editing, setEditing] = useState(true);
  return (
    <>
      <button onClick={() => navigateHash("workbench")}>进入首页</button>
      {route.page === "workbench" ? (
        <h1>首页</h1>
      ) : editing ? (
        <DashboardSettingsEditor
          dashboard={dashboard}
          onClose={() => setEditing(false)}
          onSaved={(id) => {
            setEditing(false);
            navigateHash("analysis-dashboards", {
              dashboard: dashboard.id,
              version: id,
            });
          }}
        />
      ) : (
        <h1>看板详情</h1>
      )}
    </>
  );
}

beforeEach(() => {
  window.history.replaceState({}, "", "#analysis-dashboards?dashboard=dashboard-test");
  vi.resetAllMocks();
  dashboardApi.analysisDashboardSources.mockResolvedValue(sources);
  dashboardApi.dashboardPreflight.mockResolvedValue({
    plan_hash: "plan",
    conflicts: [],
  });
  dashboardApi.updateAnalysisDashboard.mockResolvedValue({
    current_version_id: "dashboard-v2",
  });
  api.classificationResults.mockResolvedValue({
    items: [
      { version_id: "result-a", store_site: "合成店铺", listing: "A", version: 1 },
      { version_id: "result-b", store_site: "合成店铺", listing: "B", version: 1 },
    ],
    total: 21,
  });
});
afterEach(cleanup);

async function openEditor() {
  render(<Harness />);
  await waitFor(() => expect(screen.getByLabelText("看板名称")).toBeEnabled());
  await screen.findByLabelText("合成店铺 · B · v1");
}

function leave() {
  fireEvent.click(screen.getByRole("button", { name: "进入首页" }));
}

test("初始加载、来源搜索与翻页不产生未保存状态", async () => {
  await openEditor();
  fireEvent.change(screen.getByLabelText("搜索来源结果"), { target: { value: "A" } });
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  leave();
  expect(screen.getByRole("heading", { name: "首页" })).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test.each([
  [
    "名称",
    () =>
      fireEvent.change(screen.getByLabelText("看板名称"), {
        target: { value: "新名称" },
      }),
  ],
  ["来源", () => fireEvent.click(screen.getByLabelText("合成店铺 · B · v1"))],
  ["统计状态", () => fireEvent.click(screen.getByLabelText("需复核"))],
  [
    "开始日期",
    () =>
      fireEvent.change(screen.getByLabelText("反馈开始日期"), {
        target: { value: "2026-10-01" },
      }),
  ],
  [
    "结束日期",
    () =>
      fireEvent.change(screen.getByLabelText("反馈结束日期"), {
        target: { value: "2026-10-16" },
      }),
  ],
])("修改%s后离页会拦截，放弃后才跳转", async (_field, edit) => {
  await openEditor();
  edit();
  leave();
  expect(screen.getByRole("dialog", { name: "看板修改尚未保存" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "首页" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "放弃修改并离开" }));
  expect(screen.getByRole("heading", { name: "首页" })).toBeInTheDocument();
  expect(dashboardApi.updateAnalysisDashboard).not.toHaveBeenCalled();
});

test("继续编辑保留输入，改回原值后不再拦截", async () => {
  await openEditor();
  fireEvent.change(screen.getByLabelText("看板名称"), { target: { value: "新名称" } });
  leave();
  expect(screen.getByRole("dialog")).toContainElement(document.activeElement);
  fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
  expect(screen.getByLabelText("看板名称")).toHaveValue("新名称");
  fireEvent.change(screen.getByLabelText("看板名称"), {
    target: { value: "合成看板" },
  });
  leave();
  expect(screen.getByRole("heading", { name: "首页" })).toBeInTheDocument();
});

test("普通保存成功不拦截自身的新版本跳转", async () => {
  await openEditor();
  fireEvent.change(screen.getByLabelText("看板名称"), { target: { value: "新名称" } });
  fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
  await screen.findByRole("heading", { name: "看板详情" });
  expect(window.location.hash).toContain("version=dashboard-v2");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  leave();
  expect(screen.getByRole("heading", { name: "首页" })).toBeInTheDocument();
});

test("保存后离开只提交一次并保留目标路由", async () => {
  await openEditor();
  fireEvent.change(screen.getByLabelText("看板名称"), { target: { value: "新名称" } });
  leave();
  fireEvent.click(screen.getByRole("button", { name: "保存后离开" }));
  await screen.findByRole("heading", { name: "首页" });
  expect(dashboardApi.updateAnalysisDashboard).toHaveBeenCalledOnce();
  expect(window.location.hash).toBe("#workbench");
});

test("保存期间请求离开，成功后继续目标且不重复保存", async () => {
  let finish;
  dashboardApi.updateAnalysisDashboard.mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  await openEditor();
  fireEvent.change(screen.getByLabelText("看板名称"), { target: { value: "新名称" } });
  fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
  await waitFor(() =>
    expect(dashboardApi.updateAnalysisDashboard).toHaveBeenCalledOnce(),
  );
  leave();
  expect(screen.getByRole("button", { name: "继续编辑" })).toBeDisabled();
  await act(async () => finish({ current_version_id: "dashboard-v2" }));
  await screen.findByRole("heading", { name: "首页" });
  expect(dashboardApi.updateAnalysisDashboard).toHaveBeenCalledOnce();
  expect(window.location.hash).toBe("#workbench");
});

test("保存失败与表单无效时不能离开，原输入保留", async () => {
  await openEditor();
  fireEvent.change(screen.getByLabelText("看板名称"), { target: { value: "" } });
  leave();
  fireEvent.click(screen.getByRole("button", { name: "保存后离开" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "保存后离开" })).toBeEnabled(),
  );
  expect(dashboardApi.updateAnalysisDashboard).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
  fireEvent.change(screen.getByLabelText("看板名称"), {
    target: { value: "保留的名称" },
  });
  dashboardApi.updateAnalysisDashboard.mockRejectedValueOnce(new Error("合成保存失败"));
  leave();
  fireEvent.click(screen.getByRole("button", { name: "保存后离开" }));
  await screen.findByText("合成保存失败");
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(screen.getByLabelText("看板名称")).toHaveValue("保留的名称");
  expect(window.location.hash).toContain("analysis-dashboards");
});
