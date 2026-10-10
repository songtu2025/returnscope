import {
  isDashboardCreationFormValid,
  dashboardCreationPlan,
  dashboardPlanStep,
  conflictId,
} from "./dashboardCreatePolicy";
import {
  createDashboardFromPlan,
  createdDashboardRoute,
} from "./dashboardCreationRequests";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { navigateHash } from "../../app/hashRouter";
import { dashboardApi } from "../../shared/api/dashboardApi";
import {
  clearDashboardSelection,
  readDashboardSelection,
  updateDashboardSelection,
} from "./dashboardSelectionStorage";
import { errorName, errorMessage, errorStatus } from "./dashboardRequestErrors";

/** @typedef {import("./dashboardCreateContracts").DashboardSelection} DashboardSelection */
/** @typedef {import("./dashboardCreateContracts").DashboardPlan} DashboardPlan */
/** @typedef {import("./dashboardCreateContracts").DashboardCreateProps} DashboardCreateProps */

/** @param {DashboardCreateProps} props */
export function useDashboardCreation({ route, updateRoute, notify, userId }) {
  const [selection, setSelection] = useState(
    /** @returns {DashboardSelection | null} */ () =>
      readDashboardSelection(userId, route.selectionToken),
  );
  const [state, setState] = useState(
    /** @returns {{loading: boolean, error: string, plan: DashboardPlan | null}} */ () => ({
      loading: true,
      error: "",
      plan: null,
    }),
  );
  const [choices, setChoices] = useState(
    /** @returns {Record<string, string>} */ () => ({}),
  );
  const [form, setFormState] = useState(() => ({
    name: selection?.dashboard_form?.name ?? "",
    reason: selection?.target_dashboard_id
      ? (selection.dashboard_form?.reason ?? "")
      : "",
  }));
  /** @param {{name: string, reason: string}} next */
  const setForm = (next) => {
    setFormState(next);
    updateDashboardSelection(userId, route.selectionToken, (current) => ({
      ...current,
      dashboard_form: {
        name: next.name,
        ...(current.target_dashboard_id ? { reason: next.reason } : {}),
      },
    }));
  };
  const [submitting, setSubmitting] = useState(false);
  const [confirmationMessage, setConfirmationMessage] = useState("");
  const generationRef = useRef(0);
  /** @type {import("react").RefObject<AbortController | null>} */
  const controllerRef = useRef(null);
  const qualityStatuses = Array.isArray(selection?.filters?.quality_status)
    ? selection.filters.quality_status
    : ["ready"];
  /** @param {string[]} statuses */
  const setQualityStatuses = (statuses) => {
    generationRef.current += 1;
    controllerRef.current?.abort();
    const next = updateDashboardSelection(userId, route.selectionToken, (current) => ({
      ...current,
      filters: { ...current.filters, quality_status: statuses },
    }));
    setSelection(next);
    setState((current) => ({ ...current, loading: true, error: "" }));
  };

  useEffect(() => {
    const next = readDashboardSelection(userId, route.selectionToken);
    setSelection((current) =>
      JSON.stringify(current) === JSON.stringify(next) ? current : next,
    );
  }, [route.selectionToken, userId]);

  const resultVersionIds = useMemo(() => {
    const resolved = selection?.resolved_result_version_ids ?? [];
    if (resolved.length) return resolved;
    return (selection?.selected ?? []).map((item) => item.result_version_id);
  }, [selection]);

  const runPreflight = useCallback(
    /**
     * @param {string[]} ids
     * @param {boolean} [nextStep]
     */
    async (ids, nextStep = true) => {
      const generation = generationRef.current + 1;
      generationRef.current = generation;
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      setState((current) => ({ ...current, loading: true, error: "" }));
      try {
        /** @type {DashboardPlan} */
        const plan = await dashboardApi.dashboardPreflight(
          { result_version_ids: ids, filters: selection?.filters ?? {} },
          { signal: controller.signal },
        );
        if (generationRef.current !== generation) return null;
        setState({ loading: false, error: "", plan });
        setConfirmationMessage("");
        if (nextStep) {
          updateRoute({ step: dashboardPlanStep(plan) }, { replace: true });
        }
        return plan;
      } catch (error) {
        if (generationRef.current === generation && errorName(error) !== "AbortError") {
          setState((current) => ({
            ...current,
            loading: false,
            error: errorMessage(error),
          }));
        }
        return null;
      }
    },
    [selection?.filters, updateRoute],
  );

  useEffect(() => {
    if (resultVersionIds.length === 0) {
      setState({ loading: false, error: "", plan: null });
      return undefined;
    }
    runPreflight(resultVersionIds, true);
    return () => {
      generationRef.current += 1;
      controllerRef.current?.abort();
    };
  }, [resultVersionIds, runPreflight]);

  const { conflicts, blockers, warnings, currentSources, summary, isVersionCreation } =
    dashboardCreationPlan(state.plan, selection, resultVersionIds);
  const resolveConflicts = () => {
    if (conflicts.some((conflict, index) => !choices[conflictId(conflict, index)])) {
      setConfirmationMessage("请为每个冲突 Listing 选择一个结果版本。");
      return;
    }
    const candidateIds = new Set(
      conflicts.flatMap((conflict) => conflict.result_version_ids ?? []),
    );
    const resolvedIds = [
      ...resultVersionIds.filter((id) => !candidateIds.has(id)),
      ...Object.values(choices),
    ];
    const next = updateDashboardSelection(
      userId,
      route.selectionToken,
      /** @param {DashboardSelection} current */ (current) => ({
        ...current,
        resolved_result_version_ids: [...new Set(resolvedIds)],
      }),
    );
    setSelection(next);
    updateRoute({ step: "check" });
  };

  /** @param {string | undefined} targetDashboardId */
  const refreshSubmissionConflict = async (targetDashboardId) => {
    const [plan, latest] = await Promise.all([
      runPreflight(resultVersionIds, false),
      isVersionCreation && targetDashboardId
        ? dashboardApi.analysisDashboard(targetDashboardId).catch(() => null)
        : Promise.resolve(null),
    ]);
    if (latest?.revision != null) {
      const next = updateDashboardSelection(
        userId,
        route.selectionToken,
        /** @param {DashboardSelection} current */ (current) => ({
          ...current,
          expected_revision: latest.revision,
        }),
      );
      setSelection(next);
    }
    setConfirmationMessage(
      plan
        ? "数据计划已变化，已保留你的输入并刷新计划。请核对后再次确认。"
        : "数据计划已变化，已保留你的输入。请重新检查计划后再提交。",
    );
  };
  const submit = async () => {
    if (!selection) return;
    if (state.loading || state.error || state.plan?.ready !== true) return;
    if (!isDashboardCreationFormValid(form, isVersionCreation)) return;
    const targetDashboardId = selection.target_dashboard_id;
    setSubmitting(true);
    setConfirmationMessage("");
    const common = {
      result_version_ids: resultVersionIds,
      filters: selection?.filters ?? {},
      plan_hash: state.plan?.plan_hash,
      reason: isVersionCreation ? form.reason.trim() : "创建分析看板",
    };
    try {
      const created = await createDashboardFromPlan({
        selection,
        form,
        common,
        isVersionCreation,
      });
      const destination = createdDashboardRoute(created, selection);
      clearDashboardSelection(userId, route.selectionToken);
      notify(isVersionCreation ? "看板新版本已生成" : "分析看板已生成");
      navigateHash("analysis-dashboards", destination);
    } catch (error) {
      if (errorStatus(error) === 409) {
        await refreshSubmissionConflict(targetDashboardId);
      } else {
        setConfirmationMessage(errorMessage(error));
      }
    } finally {
      setSubmitting(false);
    }
  };
  return {
    selection,
    state,
    choices,
    setChoices,
    form,
    setForm,
    qualityStatuses,
    setQualityStatuses,
    submitting,
    confirmationMessage,
    resultVersionIds,
    runPreflight,
    conflicts,
    blockers,
    warnings,
    currentSources,
    summary,
    isVersionCreation,
    resolveConflicts,
    submit,
  };
}
