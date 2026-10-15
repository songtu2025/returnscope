import { useEffect, useRef, useState } from "react";
import { navigateHash } from "../../app/hashRouter";
import { dashboardApi } from "../../shared/api/dashboardApi";
import {
  clearDashboardSelection,
  readDashboardSelection,
  updateDashboardSelection,
} from "./dashboardSelectionStorage";
import { loadInsightModelOptions, insightFormForOptions } from "./insightModelOptions";
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
    /** @returns {{loading: boolean, submitting: boolean, error: string, modelError: string, models: InsightModel[]}} */ () => ({
      loading: true,
      submitting: false,
      error: "",
      modelError: "",
      models: [],
    }),
  );
  const [modelAttempt, setModelAttempt] = useState(0);
  const submissionRef = useRef(false);
  const formTokenRef = useRef(route.selectionToken);

  useEffect(() => {
    if (!isInsightCreation) return undefined;
    const restoredForm =
      formTokenRef.current !== route.selectionToken
        ? (readDashboardSelection(userId, route.selectionToken)?.insight_form ?? {
            modelId: "",
            effort: "high",
          })
        : null;
    formTokenRef.current = route.selectionToken;
    if (restoredForm) setFormState(restoredForm);
    let cancelled = false;
    const loadModels = async () => {
      setInsightState((current) => ({ ...current, loading: true, modelError: "" }));
      try {
        const options = await loadInsightModelOptions();
        if (cancelled) return;
        setFormState((current) =>
          insightFormForOptions(restoredForm ?? current, options),
        );
        setInsightState((current) => ({
          ...current,
          loading: false,
          models: options.models,
          modelError: "",
        }));
      } catch (error) {
        if (!cancelled)
          setInsightState((current) => ({
            ...current,
            loading: false,
            modelError: errorMessage(error),
          }));
      }
    };
    loadModels();
    return () => {
      cancelled = true;
    };
  }, [isInsightCreation, modelAttempt, route.selectionToken, userId]);

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
    if (
      submissionRef.current ||
      insightState.loading ||
      Boolean(insightState.modelError) ||
      !insightState.models.some((model) => model.id === insightForm.modelId) ||
      state.loading ||
      state.error ||
      state.plan?.ready !== true
    )
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
  return {
    insightForm,
    setInsightForm,
    insightState,
    submitInsight,
    reloadInsightModels: () => setModelAttempt((value) => value + 1),
  };
}
