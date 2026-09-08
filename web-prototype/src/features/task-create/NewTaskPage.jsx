import { useCallback, useEffect, useRef, useState } from "react";
import { CaretRight, Check, WarningCircle } from "@phosphor-icons/react";
import { api } from "../../api";
import { InlineLoading, PageHeading } from "../../components/SharedUi";
import { taskPlanCounts } from "../task-planning/taskPlanPolicy";
import { ProductMatchWorkbench } from "./ProductMatchWorkbench";
import { ReturnImportDialog } from "./ReturnImportDialog";
import { TaskDataStep } from "./TaskDataStep";
import { TaskConfigurationStep } from "./TaskConfigurationStep";
import { TaskPlanReviewStep } from "./TaskPlanReviewStep";

function resolveTaskModelPolicy(configs, form) {
  const publishedConfigs = configs
    .filter((item) => item.active_version)
    .map((item) => ({ ...item.active_version, connection_name: item.name }));
  const selectedConfig =
    publishedConfigs.find((item) => item.id === form.config_version_id) ??
    publishedConfigs[0];
  const selectedConnection = configs.find(
    (item) => item.id === selectedConfig?.connection_id,
  );
  return {
    connection_id: selectedConnection?.id ?? "",
    cheap_model: selectedConfig?.cheap_model ?? "",
    cheap_effort: selectedConfig?.cheap_effort ?? "low",
    primary_model: selectedConfig?.primary_model ?? "",
    primary_effort: selectedConfig?.primary_effort ?? "medium",
    secondary_model: selectedConfig?.secondary_model ?? "",
    secondary_effort: selectedConfig?.secondary_effort ?? "high",
    cheap_audit_percent: selectedConfig?.cheap_audit_percent ?? 5,
    ...form.model_policy,
  };
}

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
  const preflightRequest = useRef(0);
  const headingRef = useRef(null);
  const confirmationRef = useRef(null);
  const focusAfterPreparation = useRef(false);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);
  const [versions, setVersions] = useState([]);
  const [configs, setConfigs] = useState([]);
  const [system, setSystem] = useState(null);
  const [loadingSetup, setLoadingSetup] = useState(true);
  const [setupError, setSetupError] = useState("");
  const [setupAttempt, setSetupAttempt] = useState(0);
  const [form, setForm] = useState({
    title: "",
    dataset_version_id: "",
    product_version_id: "",
    config_version_id: "",
    store: "",
    listing: "",
    ...draft?.form,
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [preflight, setPreflight] = useState({
    status: "idle",
    data: null,
    error: "",
  });
  const [dataQuality, setDataQuality] = useState(null);
  const [unresolvedPolicy, setUnresolvedPolicy] = useState("");
  const [scopeConfirmed, setScopeConfirmed] = useState(false);
  const [segmentOrder, setSegmentOrder] = useState([]);
  const [matchingOpen, setMatchingOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [mysqlDraft, setMysqlDraft] = useState(draft?.mysqlDraft);
  const [dataEntryMode, setDataEntryMode] = useState(
    draft?.dataEntryMode ?? (draft?.form?.dataset_version_id ? "existing" : "mysql"),
  );
  const [selectedDataLabel, setSelectedDataLabel] = useState(
    draft?.selectedDataLabel ?? "",
  );

  useEffect(() => {
    setLoadingSetup(true);
    setSetupError("");
    Promise.all([
      api.dataVersions(),
      api.configs(),
      api.status(),
      api.modelPreference ? api.modelPreference() : Promise.resolve(null),
    ])
      .then(([data, connections, status, preference]) => {
        setVersions(data);
        setConfigs(connections);
        setSystem(status);
        const products = data.find((item) => item.kind === "products");
        const activeConfig = connections.find(
          (item) => item.active_version,
        )?.active_version;
        setForm((current) => ({
          ...current,
          product_version_id: current.product_version_id || products?.version_id || "",
          config_version_id:
            current.config_version_id ||
            preference?.config_version_id ||
            activeConfig?.id ||
            "",
          model_policy:
            current.model_policy ||
            (preference
              ? {
                  connection_id: preference.connection_id,
                  cheap_model: preference.cheap_model,
                  cheap_effort: preference.cheap_effort,
                  primary_model: preference.primary_model,
                  primary_effort: preference.primary_effort,
                  secondary_model: preference.secondary_model,
                  secondary_effort: preference.secondary_effort,
                }
              : undefined),
        }));
      })
      .catch((error) => setSetupError(error.message || "暂时无法读取数据与模型配置。"))
      .finally(() => setLoadingSetup(false));
  }, [setupAttempt]);

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

  const allReturns = versions
    .filter((item) => item.kind === "returns")
    .map(normalizeReturnVersion);
  const returns = canonicalManagedReturns(allReturns);
  const products = versions.filter((item) => item.kind === "products");
  const publishedConfigs = configs
    .filter((item) => item.active_version)
    .map((item) => ({ ...item.active_version, connection_name: item.name }));
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

  const invalidatePreflight = () => {
    preflightRequest.current += 1;
    focusAfterPreparation.current = false;
    setSubmitError("");
    setPreflight({ status: "idle", data: null, error: "" });
    setScopeConfirmed(false);
    setUnresolvedPolicy("");
  };

  const updateForm = (next) => {
    if (next.dataset_version_id !== form.dataset_version_id) {
      invalidatePreflight();
      setPrepared(false);
    }
    setForm(next);
  };

  const runPreflight = useCallback(async () => {
    const requestId = ++preflightRequest.current;
    setSubmitError("");
    setPreflight({ status: "loading", data: null, error: "" });
    setDataQuality(null);
    setUnresolvedPolicy("");
    setScopeConfirmed(false);
    setSegmentOrder([]);
    try {
      const [data, quality] = await Promise.all([
        api.preflightTask({
          dataset_version_id: form.dataset_version_id,
          product_version_id: form.product_version_id,
          config_version_id: form.config_version_id,
          model_policy: resolveTaskModelPolicy(configs, form),
          store: null,
          listing: null,
        }),
        api.qualityPreflight(form.dataset_version_id, form.product_version_id),
      ]);
      if (requestId !== preflightRequest.current) return;
      setDataQuality(quality);
      setPreflight({ status: "ready", data, error: "" });
      setSegmentOrder(data.segments.map((segment) => segment.segment_key));
      setUnresolvedPolicy(data.blocked_count > 0 ? "" : "block_all");
    } catch (error) {
      if (requestId !== preflightRequest.current) return;
      const message =
        error.status === 405
          ? "当前运行服务未加载任务预检能力，请重启服务后重试（PF-405）。"
          : error.message;
      setPreflight({ status: "error", data: null, error: message });
    }
  }, [configs, form]);

  useEffect(() => {
    if (
      prepared &&
      !loadingSetup &&
      form.dataset_version_id &&
      preflight.status === "idle"
    ) {
      const timer = setTimeout(runPreflight, 350);
      return () => clearTimeout(timer);
    }
  }, [form.dataset_version_id, loadingSetup, preflight.status, runPreflight, prepared]);

  useEffect(
    () => () => {
      preflightRequest.current += 1;
    },
    [],
  );

  const updateModelPolicy = (changes) => {
    invalidatePreflight();
    setForm({ ...form, model_policy: { ...modelPolicy, ...changes } });
  };
  const selectConnection = (configId) => {
    const next = publishedConfigs.find((item) => item.id === configId);
    if (!next) return;
    invalidatePreflight();
    setForm((current) => ({
      ...current,
      config_version_id: configId,
      model_policy: {
        connection_id: next.connection_id,
        cheap_model: next.cheap_model ?? "",
        cheap_effort: next.cheap_effort ?? "low",
        primary_model: next.primary_model,
        primary_effort: next.primary_effort ?? "medium",
        secondary_model: next.secondary_model ?? "",
        secondary_effort: next.secondary_effort ?? "high",
        cheap_audit_percent: next.cheap_audit_percent ?? 5,
      },
    }));
  };
  const selectedReturns = allReturns.find(
    (item) => item.version_id === form.dataset_version_id,
  );
  const selectedProducts = products.find(
    (item) => item.version_id === form.product_version_id,
  );
  const ready = products.length > 0 && publishedConfigs.length > 0;
  const planCounts = taskPlanCounts(preflight.data);
  const blocked = (preflight.data?.blocked_count ?? 0) > 0;
  const categoryCompletionRequired = Boolean(
    preflight.data?.category_completion_required,
  );
  const countMismatch = Boolean(preflight.data && !planCounts.reconciled);
  const noExecutable = Boolean(preflight.data && planCounts.executable === 0);
  const partialPlan = planCounts.notAnalyzed > 0 && planCounts.executable > 0;
  const requiresScopeConfirmation = Boolean(
    partialPlan &&
    !categoryCompletionRequired &&
    (!blocked || unresolvedPolicy === "run_ready"),
  );

  const submit = async () => {
    if (
      submitting ||
      preflight.status !== "ready" ||
      !preflight.data ||
      !unresolvedPolicy ||
      categoryCompletionRequired ||
      countMismatch ||
      noExecutable ||
      (requiresScopeConfirmation && !scopeConfirmed)
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
      if (error.status === 409) {
        setPrepared(true);
        setPreflight({
          status: "error",
          data: null,
          error: "执行计划已变化，请重新预检后再启动任务。",
        });
        setUnresolvedPolicy("");
      } else {
        setSubmitError(error.message || "暂时无法创建任务，请重试。");
      }
      notify(error.message, "error");
    } finally {
      setSubmitting(false);
    }
  };

  const resolveCategories = () => {
    const unresolvedProducts = preflight.data?.unresolved_products ?? [];
    if (
      unresolvedProducts.length > 0 &&
      unresolvedProducts.some((item) => item.editable && item.store)
    ) {
      setMatchingOpen(true);
      return;
    }
    const productVersion = products.find(
      (item) => item.version_id === form.product_version_id,
    );
    onDraftChange?.({
      form,
      step: 2,
      resumePreflight: true,
      dataEntryMode,
      selectedDataLabel,
      mysqlDraft,
    });
    onNavigate("data", {
      kind: "dataset",
      id: productVersion?.dataset_id,
      datasetKind: "products",
      returnToTask: true,
      taskTitle: form.title.trim() || "待创建分析任务",
      store: primaryPlanStore(preflight.data),
      unresolvedProducts: preflight.data?.unresolved_products ?? [],
      categoryOptions: preflight.data?.category_options ?? [],
      blockedCommentCount:
        preflight.data?.unresolved_product_comment_count ??
        preflight.data?.blocked_count ??
        0,
    });
  };

  const saveProductMatches = async (items) => {
    if (!selectedProducts?.dataset_id) return;
    setSubmitting(true);
    try {
      const updated = await api.completeProductCategories(selectedProducts.dataset_id, {
        expected_version: selectedProducts.version,
        store: primaryPlanStore(preflight.data),
        items,
        change_note: `确认任务“${
          form.title || selectedReturns?.dataset_name || "退货明细"
        }”的商品关联`,
      });
      const latestVersion = updated.versions?.find(
        (version) => version.version === updated.current_version,
      );
      if (!latestVersion?.id) {
        throw new Error("产品信息已更新，但未返回最新版本，请刷新后重试");
      }
      setVersions(await api.dataVersions());
      setMatchingOpen(false);
      invalidatePreflight();
      setForm((current) => ({
        ...current,
        product_version_id: latestVersion.id,
      }));
      notify(`已保存 ${items.length.toLocaleString()} 个商品关联，正在重新生成计划`);
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setSubmitting(false);
    }
  };

  const finishImport = async (result, source) => {
    setVersions(await api.dataVersions());
    invalidatePreflight();
    setDataEntryMode(source);
    setSelectedDataLabel(
      source === "mysql" ? "本次数据库取数快照" : importSelectionLabel(result),
    );
    setForm((current) => ({
      ...current,
      dataset_version_id: result.version_id,
      title:
        current.title ||
        `${source === "mysql" ? mysqlDraft?.store || "全部店铺" : "退货数据"} · 退货分析`,
    }));
    setUploadOpen(false);
    onChanged();
    notify(
      source === "mysql"
        ? "数据库退货明细已导入并自动选中"
        : importNotification(result),
    );
    focusAfterPreparation.current = true;
    setPrepared(true);
  };

  const canContinue =
    preflight.status === "ready" &&
    unresolvedPolicy &&
    !categoryCompletionRequired &&
    !countMismatch &&
    !noExecutable &&
    (!requiresScopeConfirmation || scopeConfirmed);

  useEffect(() => {
    // 只在用户主动准备成功后引导一次，恢复草稿和修改模型不移动焦点。
    if (prepared && canContinue && focusAfterPreparation.current && !matchingOpen) {
      focusAfterPreparation.current = false;
      confirmationRef.current?.focus();
    }
  }, [prepared, canContinue, matchingOpen]);

  const submitLabel = categoryCompletionRequired
    ? "请先补齐商品品类"
    : countMismatch
      ? "评论数量需要重新预检"
      : noExecutable
        ? "没有可执行评论"
        : blocked
          ? unresolvedPolicy === "run_ready"
            ? `启动 ${planCounts.executable.toLocaleString()} 组已就绪评论`
            : unresolvedPolicy === "block_all"
              ? "保存任务，等待问题处理"
              : "选择处理方式后继续"
          : partialPlan
            ? `启动 ${planCounts.executable.toLocaleString()} 组可执行评论`
            : "开始分析";

  let launchStatus = "确认任务名称与模型后，即可开始分析。";
  if (submitting) launchStatus = "正在创建任务，请稍候…";
  else if (submitError) launchStatus = "配置已保留，可以重试创建。";
  else if (preflight.status === "loading" || preflight.status === "idle") {
    launchStatus = "正在检查数据，不会调用模型…";
  } else if (preflight.status === "error") {
    launchStatus = "检查未完成，请在上方重新检查数据。";
  } else if (categoryCompletionRequired) launchStatus = "请先补齐上方提示的商品品类。";
  else if (countMismatch) launchStatus = "评论数量校验未通过，请重新检查数据。";
  else if (noExecutable) launchStatus = "当前范围没有可执行评论，请修改分析数据。";
  else if (blocked && !unresolvedPolicy)
    launchStatus = "请在上方选择未解决问题的处理方式。";
  else if (blocked && unresolvedPolicy === "block_all") {
    launchStatus = "仅保存任务，处理完数据问题后再开始分析。";
  } else if (requiresScopeConfirmation && !scopeConfirmed) {
    launchStatus = "请先确认上方的分析范围与排除项。";
  } else if ((system?.my_running_tasks ?? 0) >= 3) {
    launchStatus = "并行名额已满，启动后将进入队列。";
  }

  const taskActions = (
    <footer className={prepared ? "task-launch-actions" : "task-step-actions"}>
      <span role="status" id="task-action-status">
        {prepared
          ? launchStatus
          : dataEntryMode === "mysql"
            ? mysqlState.busy === "import"
              ? "正在保存本次数据…"
              : mysqlState.ready
                ? `已选 ${mysqlState.rowCount.toLocaleString()} 条退货记录`
                : "选择店铺和日期，查看本次分析范围"
            : selectedReturns
              ? `已选 ${selectedReturns.row_count.toLocaleString()} 条退货记录`
              : "请选择本次分析数据"}
      </span>
      {prepared ? (
        <button
          className="primary-button"
          disabled={submitting || !canContinue}
          aria-describedby="task-action-status"
          onClick={submit}
        >
          {submitting ? "正在创建…" : submitError ? "重试创建" : submitLabel}
        </button>
      ) : dataEntryMode === "mysql" ? (
        <button
          type="submit"
          form="mysql-prepare-form"
          className="primary-button"
          disabled={!mysqlState.ready || Boolean(mysqlState.busy)}
        >
          {mysqlState.busy === "import" ? "正在准备…" : "准备分析"}
        </button>
      ) : (
        <button
          className="primary-button"
          disabled={!selectedReturns || submitting}
          onClick={() => {
            focusAfterPreparation.current = true;
            setForm((current) => ({
              ...current,
              title: current.title || `${selectedReturns.dataset_name} · 退货分析`,
            }));
            setPrepared(true);
          }}
        >
          准备分析
        </button>
      )}
    </footer>
  );

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
    <div className="standard-page new-task-page">
      <PageHeading
        titleRef={headingRef}
        title="创建分析任务"
        description="选择退货数据，准备好后开始分析。"
      />
      {loadingSetup && (
        <section className="new-task-loading">
          <InlineLoading label="正在读取数据与模型配置…" />
        </section>
      )}
      {!loadingSetup && setupError && (
        <section className="plan-state error" role="alert">
          <WarningCircle size={20} />
          <div>
            <b>暂时无法读取创建任务所需的信息</b>
            <p>{setupError}</p>
          </div>
          <button
            className="secondary-button"
            onClick={() => setSetupAttempt((value) => value + 1)}
          >
            重新加载
          </button>
        </section>
      )}
      {!loadingSetup && !setupError && !ready && (
        <SetupBlock
          onNavigate={onNavigate}
          onUploadReturns={() => setUploadOpen(true)}
          hasReturns={returns.length > 0}
          hasProducts={products.length > 0}
          hasConfig={publishedConfigs.length > 0}
        />
      )}
      {!loadingSetup && ready && (
        <TaskDataStep
          form={form}
          onFormChange={updateForm}
          returns={returns}
          selectedReturns={selectedReturns}
          dataEntryMode={dataEntryMode}
          selectedDataLabel={selectedDataLabel}
          onDataEntryModeChange={(nextMode) => {
            if (nextMode === dataEntryMode) return;
            setDataEntryMode(nextMode);
            setSelectedDataLabel("");
            updateForm({ ...form, dataset_version_id: "" });
          }}
          onSelectedDataLabelChange={setSelectedDataLabel}
          onUploadReturns={() => setUploadOpen(true)}
          mysqlDraft={mysqlDraft}
          onMysqlDraftChange={setMysqlDraft}
          onMysqlDone={(result) => finishImport(result, "mysql")}
          onMysqlStateChange={setMysqlState}
          busy={submitting || mysqlState.busy === "import"}
          prepared={prepared}
          scopeLabel={
            dataEntryMode === "mysql"
              ? `${mysqlDraft?.store || mysqlDraft?.default_store || "全部店铺"} · ${mysqlDraft?.date_from || "不限开始日期"} — ${mysqlDraft?.date_to || "不限结束日期"}${mysqlDraft?.sku ? ` · 商品：${mysqlDraft.sku}` : ""}`
              : `${dataEntryMode === "upload" ? "上传文件" : "已有数据"} · ${selectedReturns?.dataset_name || selectedDataLabel}${selectedReturns?.version ? ` · 版本 ${selectedReturns.version}` : ""}`
          }
          onInvalidateMysql={() => {
            invalidatePreflight();
            setPrepared(false);
            setForm((current) => ({ ...current, dataset_version_id: "" }));
          }}
        >
          {prepared && (
            <TaskPlanReviewStep
              preflight={preflight}
              onRetryPreflight={runPreflight}
              categoryCompletionRequired={categoryCompletionRequired}
              blocked={blocked}
              countMismatch={countMismatch}
              noExecutable={noExecutable}
              partialPlan={partialPlan}
              planCounts={planCounts}
              dataQuality={dataQuality}
              unresolvedPolicy={unresolvedPolicy}
              onPolicyChange={(nextPolicy) => {
                setUnresolvedPolicy(nextPolicy);
                setScopeConfirmed(false);
              }}
              onResolveCategories={resolveCategories}
              segmentOrder={segmentOrder}
              onSegmentOrderChange={setSegmentOrder}
              requiresScopeConfirmation={requiresScopeConfirmation}
              scopeConfirmed={scopeConfirmed}
              onScopeConfirmationChange={setScopeConfirmed}
            />
          )}
        </TaskDataStep>
      )}
      {!loadingSetup && ready && prepared && (
        <fieldset className="task-settings-lock" disabled={submitting}>
          <TaskConfigurationStep
            headingRef={confirmationRef}
            form={form}
            onFormChange={updateForm}
            publishedConfigs={publishedConfigs}
            selectedConfig={selectedConfig}
            availableModels={availableModels}
            modelPolicy={modelPolicy}
            onConnectionChange={selectConnection}
            onModelPolicyChange={updateModelPolicy}
          >
            {submitError && (
              <div className="task-launch-error" role="alert">
                <strong>任务创建失败</strong>
                <p>{submitError}</p>
              </div>
            )}
            {taskActions}
          </TaskConfigurationStep>
        </fieldset>
      )}
      {!loadingSetup && ready && !prepared && taskActions}
      {uploadOpen && (
        <ReturnImportDialog
          onClose={() => setUploadOpen(false)}
          onDone={(result) => finishImport(result, "upload")}
        />
      )}
    </div>
  );
}

function canonicalManagedReturns(items) {
  const grouped = new Map();
  items
    .filter(
      (item) =>
        item.usage_scope !== "task_input" && item.version === item.current_version,
    )
    .forEach((item) => {
      const stores = item.quality?.stores ?? [];
      const key = item.source_key || stores.slice().sort().join("|") || item.dataset_id;
      if (!grouped.has(key)) grouped.set(key, item);
    });
  return [...grouped.values()];
}

function normalizeReturnVersion(item) {
  const stores = item.quality?.stores ?? [];
  return {
    ...item,
    dataset_name: item.source_name || returnSourceName(stores, item.dataset_name),
  };
}

function returnSourceName(stores, fallback) {
  if (!stores.length) return fallback;
  const labels = stores.map((value) => value.replace(/[:_/\\-]+/g, " ").trim());
  return `${labels.join("、")} 退货数据`;
}

function importSelectionLabel(result) {
  if (result.duplicate) return "已导入批次 · 直接复用";
  if (result.mode === "append") return "合并后的当前完整数据";
  if (result.mode === "replace") return "替换后的当前完整数据";
  if (result.mode === "create") return "新建数据源 · 当前完整数据";
  return "本次上传数据";
}

function importNotification(result) {
  if (result.duplicate) return "文件已导入过，已直接复用现有数据";
  const imported = Number(result.summary?.imported_row_count ?? 0).toLocaleString();
  const skipped = Number(result.summary?.skipped_row_count ?? 0).toLocaleString();
  return result.mode === "append"
    ? `已追加 ${imported} 行，跳过 ${skipped} 行重复记录`
    : "退货明细已导入并自动选中";
}

function primaryPlanStore(plan) {
  return (
    plan?.primary_store ||
    plan?.inputs?.scope?.store ||
    plan?.detected_scopes?.find((scope) => scope.store)?.store ||
    ""
  );
}

function SetupBlock({
  onNavigate,
  onUploadReturns,
  hasReturns,
  hasProducts,
  hasConfig,
}) {
  const rows = [
    [hasReturns, "导入退货明细", "在当前分析任务中导入待分析数据", onUploadReturns],
    [
      hasProducts,
      "维护产品信息",
      "先建立系统统一复用的产品信息",
      () => onNavigate("data"),
    ],
    [hasConfig, "发布模型配置", "先验证连接，再发布配置版本", () => onNavigate("api")],
  ];
  return (
    <section className="setup-block">
      <WarningCircle size={28} />
      <div>
        <h2>还需要完成运行准备</h2>
        <p>真实任务必须同时具备退货明细、产品信息和已发布模型配置。</p>
        <div className="setup-list">
          {rows.map(([done, title, note, action]) => (
            <button
              key={title}
              onClick={() => !done && action?.()}
              className={done ? "done" : ""}
            >
              <span>{done ? <Check size={16} /> : <CaretRight size={16} />}</span>
              <div>
                <b>{title}</b>
                <small>{note}</small>
              </div>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
