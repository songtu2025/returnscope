import { useState } from "react";
import { api } from "../../api";
import { dashboardApi } from "../../shared/api/dashboardApi";
import {
  insightModels,
  preferredInsightEffort,
  preferredInsightModel,
} from "./insightModelOptions";
import { errorMessage } from "./dashboardRequestErrors";

/** @typedef {import("./dashboardDetailContracts").InsightReport} InsightReport */
/** @typedef {import("./dashboardDetailContracts").InsightModel} InsightModel */
/** @typedef {import("./dashboardDetailContracts").DashboardDetailProps} DashboardDetailProps */

/** @param {Pick<DashboardDetailProps, "route" | "updateRoute" | "notify"> & Pick<ReturnType<typeof import("./useDashboardReports").useDashboardReports>, "setReports">} props */
export function useDashboardReportGeneration({
  route,
  updateRoute,
  notify,
  setReports,
}) {
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
  return {
    generationOpen,
    setGenerationOpen,
    generationState,
    generationForm,
    setGenerationForm,
    openReportGeneration,
    submitReportGeneration,
  };
}
