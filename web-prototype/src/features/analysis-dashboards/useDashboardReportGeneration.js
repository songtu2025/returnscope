import { useRef, useState } from "react";
import { dashboardApi } from "../../shared/api/dashboardApi";
import { loadInsightModelOptions, insightFormForOptions } from "./insightModelOptions";
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
    /** @returns {{loading: boolean, submitting: boolean, error: string, modelError: string, models: InsightModel[]}} */ () => ({
      loading: false,
      submitting: false,
      error: "",
      modelError: "",
      models: [],
    }),
  );
  const [generationForm, setGenerationForm] = useState({
    modelId: "",
    effort: "high",
  });
  const modelRequest = useRef(0);
  const reloadGenerationModels = async () => {
    const requestId = ++modelRequest.current;
    setGenerationState((current) => ({ ...current, loading: true, modelError: "" }));
    try {
      const options = await loadInsightModelOptions();
      if (requestId !== modelRequest.current) return;
      setGenerationForm((current) => insightFormForOptions(current, options));
      setGenerationState((current) => ({
        ...current,
        loading: false,
        models: options.models,
        modelError: "",
      }));
    } catch (error) {
      if (requestId !== modelRequest.current) return;
      setGenerationState((current) => ({
        ...current,
        loading: false,
        modelError: errorMessage(error) || "无法读取可用模型",
      }));
    }
  };
  const openReportGeneration = async () => {
    setGenerationState((current) => ({ ...current, submitting: false, error: "" }));
    setGenerationOpen(true);
    await reloadGenerationModels();
  };
  /** @param {import("react").FormEvent<HTMLFormElement>} event @param {{filters: Record<string, unknown>, plan_hash: string}} scope */
  const submitReportGeneration = async (event, scope) => {
    event.preventDefault();
    if (
      generationState.loading ||
      generationState.modelError ||
      !generationState.models.some((model) => model.id === generationForm.modelId)
    )
      return;
    setGenerationState((current) => ({ ...current, submitting: true, error: "" }));
    try {
      /** @type {InsightReport} */
      const report = await dashboardApi.createAnalysisDashboardInsightReport(
        route.dashboardId,
        route.versionId,
        {
          model_id: generationForm.modelId,
          reasoning_effort: generationForm.effort,
          ...scope,
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
    reloadGenerationModels,
    submitReportGeneration,
  };
}
