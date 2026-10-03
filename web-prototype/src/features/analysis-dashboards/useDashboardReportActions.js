import { useState } from "react";
import { api } from "../../api";
import { dashboardApi } from "../../shared/api/dashboardApi";
import {
  insightModels,
  preferredInsightEffort,
  preferredInsightModel,
} from "./insightModelOptions";
import { errorMessage } from "./dashboardRequestErrors";

/** @typedef {import("./dashboardDetailContracts").ReportDecision} ReportDecision */
/** @typedef {import("./dashboardDetailContracts").InsightReport} InsightReport */
/** @typedef {import("./dashboardDetailContracts").InsightModel} InsightModel */
/** @typedef {import("./dashboardDetailContracts").DashboardDetailProps} DashboardDetailProps */

/** @param {DashboardDetailProps & Pick<ReturnType<typeof import("./useDashboardReports").useDashboardReports>, "setReports" | "selectedReport">} props */
export function useDashboardReportActions({
  route,
  updateRoute,
  notify,
  setReports,
  selectedReport,
}) {
  const [decisionState, setDecisionState] = useState({
    issueId: "",
    loading: false,
    error: "",
  });
  const [generationOpen, setGenerationOpen] = useState(false);
  const [generationState, setGenerationState] = useState(
    /** @returns {{loading: boolean, submitting: boolean, error: string, models: InsightModel[]}} */ () => ({
      loading: false,
      submitting: false,
      error: "",
      models: [],
    }),
  );
  const [generationForm, setGenerationForm] = useState({
    modelId: "",
    effort: "high",
  });
  const openReportGeneration = async () => {
    setGenerationOpen(true);
    setGenerationState({ loading: true, submitting: false, error: "", models: [] });
    const [configResult, preferenceResult] = await Promise.allSettled([
      typeof api.configs === "function" ? api.configs() : Promise.resolve([]),
      typeof api.modelPreference === "function"
        ? api.modelPreference()
        : Promise.resolve(null),
    ]);
    const configs = configResult.status === "fulfilled" ? configResult.value : [];
    const preference =
      preferenceResult.status === "fulfilled" ? preferenceResult.value : null;
    /** @type {InsightModel[]} */
    const models = insightModels(configs);
    const modelId = preferredInsightModel(configs, models, preference);
    const model = models.find((item) => item.id === modelId);
    setGenerationForm({ modelId, effort: preferredInsightEffort(model) });
    setGenerationState({
      loading: false,
      submitting: false,
      error:
        configResult.status === "rejected"
          ? errorMessage(configResult.reason) || "无法读取可用模型"
          : "",
      models,
    });
  };
  /** @param {import("react").FormEvent<HTMLFormElement>} event */
  const submitReportGeneration = async (event) => {
    event.preventDefault();
    setGenerationState((current) => ({ ...current, submitting: true, error: "" }));
    try {
      /** @type {InsightReport} */
      const report = await dashboardApi.createAnalysisDashboardInsightReport(
        route.dashboardId,
        route.versionId,
        {
          model_id: generationForm.modelId,
          reasoning_effort: generationForm.effort,
        },
      );
      setReports((current) => ({
        loading: false,
        error: "",
        items: [report, ...current.items],
      }));
      setGenerationOpen(false);
      updateRoute({ reportId: report.id, issueId: "" }, { replace: true });
      notify?.("AI 洞察报告已加入生成队列");
    } catch (error) {
      setGenerationState((current) => ({
        ...current,
        submitting: false,
        error: errorMessage(error),
      }));
    }
  };
  const retryReport = async () => {
    if (!selectedReport) return;
    try {
      /** @type {InsightReport} */
      const report = await dashboardApi.retryInsightReport(selectedReport.id);
      setReports((current) => ({
        ...current,
        items: [report, ...current.items],
      }));
      updateRoute({ reportId: report.id, issueId: "" }, { replace: true });
      notify?.("新的生成尝试已加入队列，原失败记录已保留");
    } catch (error) {
      setReports((current) => ({ ...current, error: errorMessage(error) }));
    }
  };
  /**
   * @param {string} issueId
   * @param {string} status
   */
  const setIssueDecision = async (issueId, status) => {
    if (!selectedReport) return;
    setDecisionState({ issueId, loading: true, error: "" });
    try {
      /** @type {ReportDecision} */
      const decision = await dashboardApi.setInsightReportIssueDecision(
        selectedReport.id,
        issueId,
        status,
      );
      setReports((current) => ({
        ...current,
        items: current.items.map((item) => {
          if (item.id !== selectedReport.id) return item;
          const decisions = (item.decisions ?? []).filter(
            (value) => value.issue_id !== issueId,
          );
          return { ...item, decisions: [decision, ...decisions] };
        }),
      }));
      setDecisionState({ issueId: "", loading: false, error: "" });
      notify?.("问题状态已更新");
    } catch (error) {
      setDecisionState({ issueId, loading: false, error: errorMessage(error) });
    }
  };
  return {
    decisionState,
    generationOpen,
    setGenerationOpen,
    generationState,
    generationForm,
    setGenerationForm,
    openReportGeneration,
    submitReportGeneration,
    retryReport,
    setIssueDecision,
  };
}
