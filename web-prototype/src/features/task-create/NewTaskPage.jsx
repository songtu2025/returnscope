import { useEffect, useRef, useState } from "react";
import { useSWRConfig } from "swr";
import { AntdProvider } from "../../components/AntdProvider";
import { taskPlanCounts } from "../task-planning/taskPlanPolicy";
import { TaskLaunchActions } from "./NewTaskActions";
import { NewTaskView } from "./NewTaskView";
import {
  normalizeReturnVersion,
  resolveTaskModelPolicy,
  taskConnectionPolicy,
  taskConnectionSelection,
  taskDataScopeLabel,
  taskLaunchCopy,
  taskPlanViewState,
} from "./newTaskPolicy";
import { ProductMatchWorkbench } from "./ProductMatchWorkbench";
import { useNewTaskSetup } from "./useNewTaskSetup";
import { useProductMatching } from "./useProductMatching";
import { useTaskImport } from "./useTaskImport";
import { useTaskPreflight } from "./useTaskPreflight";
import { submitNewTask } from "./newTaskSubmission";

/** @typedef {import("./taskCreateContracts").TaskDraft} TaskDraft */
/** @typedef {import("./taskCreateContracts").TaskForm} TaskForm */
/**
 * @param {{onNavigate: import("../../app/navigation").Navigate, notify: (message: string, type?: "success" | "error") => void, onChanged: () => void | Promise<unknown>, draft?: TaskDraft | null, onDraftChange?: (draft: TaskDraft) => void, onDraftComplete?: () => void}} props
 */

export function NewTaskPage({
  onNavigate,
  notify,
  onChanged,
  draft,
  onDraftChange,
  onDraftComplete,
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
    configs,
    form,
    loadingSetup,
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

  const allReturns = versions
    .filter((item) => item.kind === "returns" && item.usage_scope === "task_input")
    .map(normalizeReturnVersion);
  const products = versions.filter((item) => item.kind === "products");
  const { publishedConfigs, selectedConfig, selectedConnection } =
    taskConnectionSelection(configs, form.config_version_id);
  const availableModels = (selectedConnection?.models ?? []).filter(
    (model) => model.active && model.validation_status === "validated",
  );
  const modelPolicy = resolveTaskModelPolicy(configs, form);

  const invalidateTaskPreflight = () => {
    focusAfterPreparation.current = false;
    setSubmitError("");
    invalidatePreflight();
  };
  const {
    dataEntryMode,
    finishImport,
    mysqlDraft,
    selectedDataLabel,
    setDataEntryMode,
    setMysqlDraft,
    setSelectedDataLabel,
    setUploadOpen,
    uploadOpen,
  } = useTaskImport({
    draft,
    focusAfterPreparationRef: focusAfterPreparation,
    invalidatePreflight: invalidateTaskPreflight,
    notify,
    onChanged,
    setForm,
    setPrepared,
    setVersions,
  });

  useEffect(() => {
    onDraftChange?.({
      form,
      step: prepared ? 2 : 1,
      resumePreflight: prepared,
      dataEntryMode,
      selectedDataLabel,
      mysqlDraft,
    });
  }, [dataEntryMode, form, mysqlDraft, onDraftChange, selectedDataLabel, prepared]);

  /** @param {TaskForm} next */
  const updateForm = (next) => {
    if (next.dataset_version_id !== form.dataset_version_id) {
      invalidateTaskPreflight();
      setPrepared(false);
    }
    setForm(next);
  };

  /** @param {Record<string, string | number>} changes */
  const updateModelPolicy = (changes) => {
    invalidateTaskPreflight();
    setForm({ ...form, model_policy: { ...modelPolicy, ...changes } });
  };
  /** @param {string} configId */
  const selectConnection = (configId) => {
    const modelPolicy = taskConnectionPolicy(publishedConfigs, configId);
    if (!modelPolicy) return;
    invalidateTaskPreflight();
    setForm((current) => ({
      ...current,
      config_version_id: configId,
      model_policy: modelPolicy,
    }));
  };
  const selectedReturns = allReturns.find(
    (item) => item.version_id === form.dataset_version_id,
  );
  useEffect(() => {
    if (loadingSetup || setupError || !form.dataset_version_id || selectedReturns)
      return;
    setPrepared(false);
    invalidatePreflight();
    setForm((current) => ({ ...current, dataset_version_id: "" }));
    notify(
      "草稿中的分析数据已失效，请重新读取数据库或上传文件；其他设置已保留。",
      "error",
    );
  }, [
    loadingSetup,
    setupError,
    form.dataset_version_id,
    selectedReturns,
    invalidatePreflight,
    setForm,
    notify,
  ]);
  const selectedProducts = products.find(
    (item) => item.version_id === form.product_version_id,
  );
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
  const planCounts = taskPlanCounts(preflight.data);
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

  const canContinue = planState.canContinue;

  useEffect(() => {
    // 只在用户主动准备成功后引导一次，恢复草稿和修改模型不移动焦点。
    if (prepared && canContinue && focusAfterPreparation.current && !matchingOpen) {
      focusAfterPreparation.current = false;
      confirmationRef.current?.focus();
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
      dataEntryMode={dataEntryMode}
      mysqlState={mysqlState}
      selectedReturns={selectedReturns}
      submitting={submitting}
      canContinue={canContinue}
      launchStatus={launchStatus}
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
        headingRef={headingRef}
        setup={{
          loading: loadingSetup,
          error: setupError,
          ready,
          onRetry: setSetupAttempt,
          onNavigate,
          products,
          publishedConfigs,
        }}
        data={{
          form,
          updateForm,
          selectedReturns,
          dataEntryMode,
          selectedDataLabel,
          onDataEntryModeChange: (/** @type {"mysql" | "upload"} */ nextMode) => {
            if (nextMode === dataEntryMode) return;
            setDataEntryMode(nextMode);
            setSelectedDataLabel("");
            updateForm({ ...form, dataset_version_id: "" });
          },
          mysqlDraft,
          setMysqlDraft,
          setMysqlState,
          mysqlState,
          prepared,
          scopeLabel,
          onInvalidateMysql: () => {
            invalidateTaskPreflight();
            setPrepared(false);
            setForm((current) => ({ ...current, dataset_version_id: "" }));
          },
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
        upload={{
          open: uploadOpen,
          onOpen: () => setUploadOpen(true),
          onClose: () => setUploadOpen(false),
          onDone: finishImport,
        }}
        taskActions={taskActions}
      />
    </AntdProvider>
  );
}
