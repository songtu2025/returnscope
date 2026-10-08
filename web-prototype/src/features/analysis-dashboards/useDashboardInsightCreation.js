import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { navigateHash } from "../../app/hashRouter";
import { dashboardApi } from "../../shared/api/dashboardApi";
import {
  clearDashboardSelection,
  updateDashboardSelection,
} from "./dashboardSelectionStorage";
import {
  insightModels,
  preferredInsightEffort,
  preferredInsightModel,
} from "./insightModelOptions";
import { errorMessage, errorStatus } from "./dashboardRequestErrors";

/** @typedef {import("./dashboardCreateContracts").DashboardCreateContext} DashboardCreateContext */
/** @typedef {import("./analysisDashboardContracts").InsightGenerationForm} InsightGenerationForm */
/** @typedef {import("./analysisDashboardContracts").InsightModel} InsightModel */

/** @param {DashboardCreateContext & {isInsightCreation: boolean}} context */
export function useDashboardInsightCreation(context) {
  const {
    isInsightCreation,
    selection,
    route,
    userId,
    state,
    resultVersionIds,
    runPreflight,
    notify,
  } = context;
  const [insightForm, setFormState] = useState(
    () => selection?.insight_form ?? { modelId: "", effort: "high" },
  );
  const [insightState, setInsightState] = useState(
    /** @returns {{loading: boolean, submitting: boolean, error: string, models: InsightModel[]}} */ () => ({
      loading: true,
      submitting: false,
      error: "",
      models: [],
    }),
  );
  const submissionRef = useRef(false);
  const savedForm = selection?.insight_form;

  useEffect(() => {
    if (!isInsightCreation) return undefined;
    let cancelled = false;
    const loadModels = async () => {
      const [configResult, preferenceResult] = await Promise.allSettled([
        api.configs(),
        typeof api.modelPreference === "function"
          ? api.modelPreference()
          : Promise.resolve(null),
      ]);
      if (cancelled) return;
      const configs = configResult.status === "fulfilled" ? configResult.value : [];
      const preference =
        preferenceResult.status === "fulfilled" ? preferenceResult.value : null;
      const models = insightModels(configs);
      const savedModel = models.find((model) => model.id === savedForm?.modelId);
      const modelId =
        savedModel?.id || preferredInsightModel(configs, models, preference);
      const model = models.find((item) => item.id === modelId);
      setFormState({
        modelId,
        effort:
          savedForm && model?.supported_efforts?.includes(savedForm.effort)
            ? savedForm.effort
            : preferredInsightEffort(model),
      });
      setInsightState({
        loading: false,
        submitting: false,
        models,
        error:
          configResult.status === "rejected" ? errorMessage(configResult.reason) : "",
      });
    };
    loadModels();
    return () => {
      cancelled = true;
    };
  }, [isInsightCreation, savedForm]);

  /** @param {InsightGenerationForm} next */
  const setInsightForm = (next) => {
    setFormState(next);
    updateDashboardSelection(userId, route.selectionToken, (current) => ({
      ...current,
      insight_form: next,
    }));
  };

  /** @param {import("react").FormEvent<HTMLFormElement>} event */
  const submitInsight = async (event) => {
    event.preventDefault();
    if (submissionRef.current || !insightForm.modelId || state.plan?.ready !== true)
      return;
    submissionRef.current = true;
    setInsightState((current) => ({ ...current, submitting: true, error: "" }));
    try {
      const created = await dashboardApi.createInsightReportFromResults({
        result_version_ids: resultVersionIds,
        filters: selection?.filters ?? {},
        plan_hash: state.plan.plan_hash,
        model_id: insightForm.modelId,
        reasoning_effort: insightForm.effort,
      });
      clearDashboardSelection(userId, route.selectionToken);
      notify("AI 洞察报告已加入生成队列");
      navigateHash("analysis-dashboards", {
        dashboard: created.dashboard.id,
        version: created.dashboard.version.version_id,
        tab: "report",
        report: created.report.id,
      });
    } catch (error) {
      if (errorStatus(error) === 409) {
        await runPreflight(resultVersionIds);
      }
      setInsightState((current) => ({
        ...current,
        submitting: false,
        error:
          errorStatus(error) === 409
            ? "数据计划已变化，已保留模型选择并重新检查。请核对后再次确认。"
            : errorMessage(error),
      }));
    } finally {
      submissionRef.current = false;
    }
  };
  return { insightForm, setInsightForm, insightState, submitInsight };
}
