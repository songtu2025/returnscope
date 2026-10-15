import { useState } from "react";
import { act, cleanup, screen, waitFor, renderHook } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { renderWithServerState as render } from "./renderWithServerState";
import { useDashboardInsightCreation } from "../src/features/analysis-dashboards/useDashboardInsightCreation";
import { useDashboardReportGeneration } from "../src/features/analysis-dashboards/useDashboardReportGeneration";
import { DashboardInsightConfirmation } from "../src/features/analysis-dashboards/DashboardInsightConfirmation";
import { insightFormForOptions } from "../src/features/analysis-dashboards/insightModelOptions";
import { DashboardReportGeneration } from "../src/features/analysis-dashboards/DashboardReportGeneration";
import {
  createDashboardSelection,
  readDashboardSelection,
} from "../src/features/analysis-dashboards/dashboardSelectionStorage";

const mocks = vi.hoisted(() => ({
  configs: vi.fn(),
  modelPreference: vi.fn(),
  dashboardPreflight: vi.fn(),
  createInsightReportFromResults: vi.fn(),
  createAnalysisDashboardInsightReport: vi.fn(),
  runPreflight: vi.fn(),
}));
vi.mock("../src/api", () => ({ api: mocks }));
vi.mock("../src/shared/api/dashboardApi", () => ({ dashboardApi: mocks }));
const savedForm = { modelId: "model-two", effort: "medium" };
const source = {
  result_version_id: "version-one",
  listing: "TEST",
  store_site: "TEST:US",
  record_count: 5,
  unit_count: 2,
};
const configs = [
  {
    id: "connection",
    name: "合成接入",
    active_version: { primary_model: "model-one" },
    models: ["one", "two"].map((key) => ({
      id: `model-${key}`,
      connection_id: "connection",
      model_key: `model-${key}`,
      display_name: `模型${key}`,
      active: true,
      validation_status: "validated",
      supported_efforts: ["low", "medium", "high"],
    })),
  },
];
const summary = { record_count: 5, unit_count: 2 };
let token;
let selection;
beforeEach(() => {
  vi.resetAllMocks();
  sessionStorage.clear();
  selection = {
    selected: [source],
    insight_form: savedForm,
    filters: { quality_status: ["ready"], product_name: "合成产品" },
  };
  token = createDashboardSelection("user", selection);
  mocks.configs.mockResolvedValue(configs);
  mocks.modelPreference.mockResolvedValue({
    connection_id: "connection",
    primary_model: "model-one",
  });
  mocks.dashboardPreflight.mockResolvedValue({
    ready: true,
    plan_hash: "plan",
    summary,
  });
});
afterEach(cleanup);

function ResultsEntry() {
  const [qualityStatuses, setQualityStatuses] = useState(["ready"]);
  const context = {
    isInsightCreation: true,
    selection,
    route: { selectionToken: token },
    userId: "user",
    state: { loading: false, error: "", plan: { ready: true, plan_hash: "plan" } },
    resultVersionIds: ["version-one"],
    runPreflight: mocks.runPreflight,
    notify: vi.fn(),
    currentSources: [source],
    summary,
    blockers: [],
    qualityStatuses,
    setQualityStatuses,
  };
  const insight = useDashboardInsightCreation(context);
  return <DashboardInsightConfirmation {...context} {...insight} />;
}
function DashboardEntry() {
  const report = useDashboardReportGeneration({
    route: { dashboardId: "dashboard", versionId: "version" },
    updateRoute: vi.fn(),
    notify: vi.fn(),
    setReports: vi.fn(),
  });
  return (
    <>
      <button
        onClick={() => {
          report.setGenerationForm(savedForm);
          void report.openReportGeneration();
        }}
      >
        打开生成
      </button>
      {report.generationOpen && (
        <DashboardReportGeneration
          {...report}
          dashboard={{ name: "合成看板" }}
          selectedVersion={{ source_snapshot: [source], filters: selection.filters }}
          analysisContext="user_feedback"
        />
      )}
    </>
  );
}
async function open(entry) {
  render(entry === "结果池" ? <ResultsEntry /> : <DashboardEntry />);
  if (entry === "看板")
    await userEvent.click(screen.getByRole("button", { name: "打开生成" }));
}

test.each(["结果池", "看板"])(
  "%s模型失败可独立重试，重试期间范围不卸载且选择/模型草稿不丢",
  async (entry) => {
    mocks.configs.mockRejectedValueOnce(new Error("合成模型读取失败"));
    await open(entry);
    const retry = await screen.findByRole("button", { name: "重新读取模型" });
    expect(screen.getByRole("button", { name: "开始生成" })).toBeDisabled();
    expect(screen.queryByText("请联系管理员配置并验证模型")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("option", { name: "暂无可用模型" }),
    ).not.toBeInTheDocument();
    const include = screen.getByRole("checkbox", { name: "需复核" });
    await userEvent.click(include);
    const preflightCount = mocks.dashboardPreflight.mock.calls.length;
    let finish;
    mocks.configs.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    await userEvent.click(retry);
    expect(screen.getByRole("checkbox", { name: "需复核" })).toBe(include);
    expect(include).toBeChecked();
    expect(screen.getByRole("button", { name: "开始生成" })).toBeDisabled();
    await act(async () => finish(configs));
    await waitFor(() => expect(screen.getByLabelText("模型")).toHaveValue("model-two"));
    expect(screen.getByRole("button", { name: "中", exact: true })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(include).toBeChecked();
    expect(
      screen.queryByRole("button", { name: "重新读取模型" }),
    ).not.toBeInTheDocument();
    expect(mocks.dashboardPreflight).toHaveBeenCalledTimes(preflightCount);
    expect(mocks.runPreflight).not.toHaveBeenCalled();
    expect(mocks.createInsightReportFromResults).not.toHaveBeenCalled();
    expect(mocks.createAnalysisDashboardInsightReport).not.toHaveBeenCalled();
    expect(readDashboardSelection("user", token)).toMatchObject(selection);
  },
);

test.each(["结果池", "看板"])("%s成功读取空模型清单与网络失败区分", async (entry) => {
  mocks.configs.mockResolvedValue([]);
  await open(entry);
  expect(await screen.findByText("请联系管理员配置并验证模型")).toBeVisible();
  expect(screen.getByRole("option", { name: "暂无可用模型" })).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "重新读取模型" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByText(/模型读取失败/)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "开始生成" })).toBeDisabled();
});

test.each(["结果池", "看板"])("%s偏好读取失败不阻断目录和原模型选择", async (entry) => {
  mocks.modelPreference.mockRejectedValue(new Error("合成偏好读取失败"));
  await open(entry);
  await waitFor(() => expect(screen.getByLabelText("模型")).toHaveValue("model-two"));
  expect(
    screen.queryByRole("button", { name: "重新读取模型" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "中", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByRole("button", { name: "开始生成" })).toBeEnabled();
});

test("目录变化仅在原模型不可用时回退，仍保留支持的推理强度", () => {
  const options = { models: configs[0].models, preferredModelId: "model-one" };
  expect(insightFormForOptions(savedForm, options)).toEqual(savedForm);
  expect(
    insightFormForOptions(savedForm, { ...options, models: [configs[0].models[0]] }),
  ).toEqual({ modelId: "model-one", effort: "medium" });
});

test("看板生成成功后重新打开仍可读取模型，保留选择而不残留提交忙态", async () => {
  const view = renderHook(() =>
    useDashboardReportGeneration({
      route: { dashboardId: "dashboard", versionId: "version" },
      updateRoute: vi.fn(),
      notify: vi.fn(),
      setReports: vi.fn(),
    }),
  );
  await act(() => view.result.current.openReportGeneration());
  act(() => view.result.current.setGenerationForm(savedForm));
  mocks.createAnalysisDashboardInsightReport.mockResolvedValue({ id: "report" });
  await act(() =>
    view.result.current.submitReportGeneration(
      { preventDefault: vi.fn() },
      { filters: { quality_status: ["ready"] }, plan_hash: "plan" },
    ),
  );
  expect(view.result.current.generationOpen).toBe(false);
  await act(() => view.result.current.openReportGeneration());
  expect(view.result.current.generationState).toMatchObject({
    loading: false,
    submitting: false,
    modelError: "",
    error: "",
  });
  expect(view.result.current.generationForm).toEqual(savedForm);
});

test("切换结果选择会话时恢复该会话模型草稿，不沿用上一会话", async () => {
  const view = render(<ResultsEntry />);
  await waitFor(() => expect(screen.getByLabelText("模型")).toHaveValue("model-two"));
  selection = { ...selection, insight_form: { modelId: "model-one", effort: "low" } };
  token = createDashboardSelection("user", selection);
  view.rerender(<ResultsEntry />);
  await waitFor(() => expect(screen.getByLabelText("模型")).toHaveValue("model-one"));
  expect(screen.getByRole("button", { name: "低", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});
