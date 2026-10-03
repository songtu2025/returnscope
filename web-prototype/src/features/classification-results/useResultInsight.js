import { useState } from "react";
import { api } from "../../api";
import { navigateHash } from "../../app/hashRouter";
import { dashboardApi } from "../../shared/api/dashboardApi";
import {
  insightModels,
  preferredInsightEffort,
  preferredInsightModel,
} from "../analysis-dashboards/insightModelOptions";

/** @typedef {import("./classificationResultListContracts").DashboardSelectionItem} DashboardSelectionItem */
/** @typedef {import("./classificationResultListContracts").InsightState} InsightState */
/** @typedef {import("./classificationResultListContracts").InsightForm} InsightForm */
/** @typedef {import("./classificationResultListContracts").ClassificationResultListProps} ClassificationResultListProps */

/** @param {Pick<ClassificationResultListProps,"notify"> & {selectedResults:DashboardSelectionItem[],clearSelection:(exit?:boolean)=>void}} props */
export function useResultInsight({ notify, selectedResults, clearSelection }) {
  const [insightOpen, setInsightOpen] = useState(false);
  const [insightState, setInsightState] = useState(
    /** @type {InsightState} */ ({
      loading: false,
      submitting: false,
      error: "",
      plan: null,
      models: [],
    }),
  );
  const [insightForm, setInsightForm] = useState(
    /** @type {InsightForm} */ ({
      modelId: "",
      effort: "high",
    }),
  );

  const openInsightDialog = async () => {
    if (!selectedResults.length) return;
    setInsightOpen(true);
    setInsightState({
      loading: true,
      submitting: false,
      error: "",
      plan: null,
      models: [],
    });
    const ids = selectedResults.map((item) => item.result_version_id);
    const configRequest =
      typeof api.configs === "function" ? api.configs() : Promise.resolve([]);
    const preferenceRequest =
      typeof api.modelPreference === "function"
        ? api.modelPreference()
        : Promise.resolve(null);
    const [planResult, configResult, preferenceResult] = await Promise.allSettled([
      dashboardApi.dashboardPreflight({
        result_version_ids: ids,
        filters: {},
      }),
      configRequest,
      preferenceRequest,
    ]);
    const plan = planResult.status === "fulfilled" ? planResult.value : null;
    const configs = configResult.status === "fulfilled" ? configResult.value : [];
    const preference =
      preferenceResult.status === "fulfilled" ? preferenceResult.value : null;
    const models = insightModels(configs);
    const modelId = preferredInsightModel(configs, models, preference);
    const selectedModel = models.find((model) => model.id === modelId);
    setInsightForm({
      modelId,
      effort: preferredInsightEffort(selectedModel),
    });
    setInsightState({
      loading: false,
      submitting: false,
      error:
        planResult.status === "rejected"
          ? planResult.reason?.message || "无法读取本次分析范围"
          : "",
      plan,
      models,
    });
  };

  /** @param {import("react").FormEvent<HTMLFormElement>} event */
  const submitInsight = async (event) => {
    event.preventDefault();
    if (!insightForm.modelId || insightState.plan?.ready !== true) return;
    setInsightState((current) => ({ ...current, submitting: true, error: "" }));
    try {
      const created = await dashboardApi.createInsightReportFromResults({
        result_version_ids: selectedResults.map((item) => item.result_version_id),
        filters: insightState.plan.filters ?? {},
        plan_hash: insightState.plan.plan_hash,
        model_id: insightForm.modelId,
        reasoning_effort: insightForm.effort,
      });
      clearSelection(false);
      setInsightOpen(false);
      notify?.("AI 洞察报告已加入生成队列");
      navigateHash("analysis-dashboards", {
        dashboard: created.dashboard.id,
        version: created.dashboard.version.version_id,
        tab: "report",
        report: created.report.id,
      });
    } catch (error) {
      setInsightState((current) => ({
        ...current,
        submitting: false,
        error: error instanceof Error ? error.message : "请求失败",
      }));
    }
  };

  return {
    insightOpen,
    setInsightOpen,
    insightState,
    insightForm,
    setInsightForm,
    openInsightDialog,
    submitInsight,
  };
}
