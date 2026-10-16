import { useEffect, useRef, useState } from "react";
import { useSWRConfig } from "swr";
import { AntdProvider } from "../../components/AntdProvider";
import { taskPlanCounts } from "../task-planning/taskPlanPolicy";
import { TaskLaunchActions } from "./NewTaskActions";
import { NewTaskView } from "./NewTaskView";
import {
  taskConnectionPolicy,
  taskDataScopeLabel,
  taskLaunchCopy,
  taskPlanViewState,
  taskModelPolicyError,
} from "./newTaskPolicy";
import { ProductMatchWorkbench } from "./ProductMatchWorkbench";
import { useNewTaskSetup } from "./useNewTaskSetup";
import { useProductMatching } from "./useProductMatching";
import { useTaskImport } from "./useTaskImport";
import { useTaskPreflight } from "./useTaskPreflight";
import { submitNewTask } from "./newTaskSubmission";

/** @typedef {import("./taskCreateContracts").TaskDraft} TaskDraft */
/**
 * @param {{onNavigate: import("../../app/navigation").Navigate, canManageModels?: boolean, notify: (message: string, type?: "success" | "error") => void, onChanged: () => void | Promise<unknown>, draft?: TaskDraft | null, onDraftChange?: (draft: TaskDraft) => void, onDraftComplete?: () => void, onDiscard?: () => void}} props
 */

export function NewTaskPage({
  onNavigate,
  canManageModels = false,
  notify,
  onChanged,
  draft,
  onDraftChange,
  onDraftComplete,
  onDiscard,
}) {
  const { mutate: mutateServerState } = useSWRConfig();
  const [prepared, setPrepared] = useState(Boolean(draft?.resumePreflight));
  const [mysqlState, setMysqlState] = useState({ ready: false, busy: "", rowCount: 0 });
  const headingRef = useRef(/** @type {HTMLHeadingElement | null} */ (null));
  const confirmationRef = useRef(/** @type {HTMLHeadingElement | null} */ (null));
  const focusAfterPreparation = useRef(false);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);
  const {
    availableModels,
    configs,
    form,
    loadingSetup,
    modelPolicy,
    products,
    publishedConfigs,
    selectedConfig,
    selectedProducts,
    setForm,
    setSetupAttempt,
    setVersions,
    setupError,
    system,
    versions,
  } = useNewTaskSetup(draft);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const {
    dataQuality,
    invalidatePreflight,
    preflight,
    runPreflight,
    scopeConfirmed,
    segmentOrder,
    segmentSelection,
    setPreflight,
    setScopeConfirmed,
    setSegmentOrder,
    setUnresolvedPolicy,
    unresolvedPolicy,
  } = useTaskPreflight({
    configs,
    form,
    loadingSetup,
    prepared,
    setSubmitError,
  });

  const invalidateTaskPreflight = () => {
    focusAfterPreparation.current = false;
    setSubmitError("");
    invalidatePreflight();
  };
  const {
    changeDataEntryMode,
    dataEntryMode,
    invalidateMysql,
    mysqlDraft,
    selectedDataLabel,
    selectedReturns,
    setMysqlDraft,
    updateForm,
    upload,
  } = useTaskImport({
    draft,
    focusAfterPreparationRef: focusAfterPreparation,
    form,
    invalidatePreflight: invalidateTaskPreflight,
    invalidateUnavailableSource: invalidatePreflight,
    loadingSetup,
    notify,
    onChanged,
    onDraftChange,
    prepared,
    setForm,
    setPrepared,
    setVersions,
    setupError,
    versions,
  });

  /** @param {Record<string, string | number>} changes */
  const updateModelPolicy = (changes) => {
    setSubmitError("");
    setForm({ ...form, model_policy: { ...modelPolicy, ...changes } });
  };
  /** @param {string} configId */
  const selectConnection = (configId) => {
    const policy = taskConnectionPolicy(publishedConfigs, configId);
    if (!policy) return;
    setSubmitError("");
    updateForm({ ...form, config_version_id: configId, model_policy: policy });
  };
  const { matchingOpen, resolveCategories, saveProductMatches, setMatchingOpen } =
    useProductMatching({
      dataEntryMode,
      form,
      invalidatePreflight: invalidateTaskPreflight,
      mysqlDraft,
      notify,
      onDraftChange,
      onNavigate,
      preflight,
      products,
      selectedDataLabel,
      selectedProducts,
      selectedReturns,
      setForm,
      setSubmitting,
      setVersions,
    });
  const ready = products.length > 0 && publishedConfigs.length > 0;
  const planCounts = taskPlanCounts(preflight.data, segmentSelection.keys);
  const planState = taskPlanViewState(
    { ...preflight, counts: planCounts },
    unresolvedPolicy,
    scopeConfirmed,
  );

  const submit = () =>
    submitNewTask({
      submitting,
      preflight,
      unresolvedPolicy,
      planState,
      scopeConfirmed,
      form,
      segmentOrder,
      selectedSegmentKeys: segmentSelection.keys,
      mutateServerState,
      setSubmitting,
      setSubmitError,
      setPrepared,
      setPreflight,
      setUnresolvedPolicy,
      notify,
      onDraftComplete,
      onChanged,
      onNavigate,
    });

  const modelError = taskModelPolicyError(availableModels, modelPolicy);
  const canContinue = planState.canContinue && !modelError;

  useEffect(() => {
    // 只在用户主动准备成功后引导一次，恢复草稿和修改模型不移动焦点。
    if (prepared && canContinue && focusAfterPreparation.current && !matchingOpen) {
      focusAfterPreparation.current = false;
      headingRef.current?.focus();
    }
  }, [prepared, canContinue, matchingOpen]);

  const { launchStatus, submitLabel } = taskLaunchCopy({
    ...planState,
    planCounts,
    preflightStatus: preflight.status,
    scopeConfirmed,
    submitError,
    submitting,
    system,
    unresolvedPolicy,
  });

  const taskActions = (
    <TaskLaunchActions
      prepared={prepared}
      planCounts={preflight.data ? planCounts : undefined}
      dataEntryMode={dataEntryMode}
      mysqlState={mysqlState}
      selectedReturns={selectedReturns}
      submitting={submitting}
      canContinue={canContinue}
      launchStatus={modelError || launchStatus}
      submitError={submitError}
      submitLabel={submitLabel}
      onSubmit={submit}
    />
  );
  const scopeLabel = taskDataScopeLabel({
    dataEntryMode,
    mysqlDraft,
    selectedReturns,
    selectedDataLabel,
  });

  if (!loadingSetup && ready && matchingOpen && preflight.data) {
    return (
      <ProductMatchWorkbench
        plan={preflight.data}
        saving={submitting}
        onBack={() => setMatchingOpen(false)}
        onSave={saveProductMatches}
      />
    );
  }

  return (
    <AntdProvider>
      <NewTaskView
        onDiscard={onDiscard}
        headingRef={headingRef}
        setup={{
          loading: loadingSetup,
          error: setupError,
          ready,
          onRetry: setSetupAttempt,
          onNavigate,
          products,
          publishedConfigs,
          canManageModels,
        }}
        data={{
          form,
          updateForm,
          selectedReturns,
          dataEntryMode,
          selectedDataLabel,
          onDataEntryModeChange: changeDataEntryMode,
          mysqlDraft,
          setMysqlDraft,
          setMysqlState,
          mysqlState,
          prepared,
          scopeLabel,
          onInvalidateMysql: invalidateMysql,
        }}
        plan={{
          preflight,
          runPreflight,
          state: planState,
          counts: planCounts,
          dataQuality,
          unresolvedPolicy,
          onPolicyChange: (/** @type {string} */ nextPolicy) => {
            setUnresolvedPolicy(nextPolicy);
            setScopeConfirmed(false);
          },
          resolveCategories,
          segmentOrder,
          segmentSelection,
          setSegmentOrder,
          scopeConfirmed,
          setScopeConfirmed,
        }}
        configuration={{
          confirmationRef,
          selectedConfig,
          availableModels,
          modelPolicy,
          selectConnection,
          updateModelPolicy,
          submitError,
          submitting,
        }}
        upload={upload}
        taskActions={taskActions}
      />
    </AntdProvider>
  );
}
