import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { AntdProvider } from "../../components/AntdProvider";
import { taskPlanCounts } from "../task-planning/taskPlanPolicy";
import { TaskLaunchActions } from "./NewTaskActions";
import { NewTaskView } from "./NewTaskView";
import {
  canonicalManagedReturns,
  normalizeReturnVersion,
  resolveTaskModelPolicy,
  taskConnectionPolicy,
  taskLaunchCopy,
  taskPlanViewState,
} from "./newTaskPolicy";
import { ProductMatchWorkbench } from "./ProductMatchWorkbench";
import { useNewTaskSetup } from "./useNewTaskSetup";
import { useProductMatching } from "./useProductMatching";
import { useTaskImport } from "./useTaskImport";
import { useTaskPreflight } from "./useTaskPreflight";

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
    .filter((item) => item.kind === "returns")
    .map(normalizeReturnVersion);
  const returns = canonicalManagedReturns(allReturns);
  const products = versions.filter((item) => item.kind === "products");
  const publishedConfigs = configs.flatMap((item) =>
    item.active_version ? [{ ...item.active_version, connection_name: item.name }] : [],
  );
  const selectedConfig =
    publishedConfigs.find((item) => item.id === form.config_version_id) ??
    publishedConfigs[0];
  const selectedConnection = configs.find(
    (item) => item.id === selectedConfig?.connection_id,
  );
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

  const submit = async () => {
    if (
      submitting ||
      preflight.status !== "ready" ||
      !preflight.data ||
      !unresolvedPolicy ||
      planState.categoryCompletionRequired ||
      planState.countMismatch ||
      planState.noExecutable ||
      (planState.requiresScopeConfirmation && !scopeConfirmed)
    ) {
      return;
    }
    setSubmitting(true);
    setSubmitError("");
    try {
      await api.createTask({
        ...form,
        store: null,
        listing: null,
        title: form.title.trim(),
        plan_hash: preflight.data.plan_hash,
        unresolved_policy: unresolvedPolicy,
        segment_order: segmentOrder,
      });
      notify("任务已创建，后台执行器会自动领取");
      onDraftComplete?.();
      onChanged();
      onNavigate("tasks");
    } catch (error) {
      const status =
        typeof error === "object" && error !== null && "status" in error
          ? error.status
          : undefined;
      const message =
        error instanceof Error ? error.message : "暂时无法创建任务，请重试。";
      if (status === 409) {
        setPrepared(true);
        setPreflight({
          status: "error",
          data: null,
          error: "执行计划已变化，请重新预检后再启动任务。",
        });
        setUnresolvedPolicy("");
      } else {
        setSubmitError(message);
      }
      notify(message, "error");
    } finally {
      setSubmitting(false);
    }
  };

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
      onPrepareExisting={() => {
        if (!selectedReturns) return;
        focusAfterPreparation.current = true;
        setForm((current) => ({
          ...current,
          title: current.title || `${selectedReturns.dataset_name} · 用户语义分析`,
        }));
        setPrepared(true);
      }}
    />
  );
  const scopeLabel =
    dataEntryMode === "mysql"
      ? `${mysqlDraft?.store || mysqlDraft?.default_store || "全部店铺"} · ${mysqlDraft?.date_from || "不限开始日期"} — ${mysqlDraft?.date_to || "不限结束日期"}${mysqlDraft?.sku ? ` · 商品：${mysqlDraft.sku}` : ""}`
      : `${dataEntryMode === "upload" ? "上传文件" : "已有数据"} · ${selectedReturns?.dataset_name || selectedDataLabel}${selectedReturns?.version ? ` · 版本 ${selectedReturns.version}` : ""}`;

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
          returns,
          products,
          publishedConfigs,
        }}
        data={{
          form,
          updateForm,
          selectedReturns,
          dataEntryMode,
          selectedDataLabel,
          onDataEntryModeChange: (
            /** @type {"mysql" | "upload" | "existing"} */ nextMode,
          ) => {
            if (nextMode === dataEntryMode) return;
            setDataEntryMode(nextMode);
            setSelectedDataLabel("");
            updateForm({ ...form, dataset_version_id: "" });
          },
          setSelectedDataLabel,
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
