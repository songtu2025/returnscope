import { useCallback, useEffect, useState } from "react";
import { CaretRight, Check, WarningCircle } from "@phosphor-icons/react";
import { api } from "../../api";
import { DatasetUploadDialog } from "../../components/DatasetUploadDialog";
import { InlineLoading, PageHeading } from "../../components/SharedUi";
import { taskPlanCounts } from "../task-planning/taskPlanPolicy";
import { classNames } from "../../lib/presentation";
import { ProductMatchWorkbench } from "./ProductMatchWorkbench";
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
  const [step, setStep] = useState(draft?.step === 3 ? 3 : 1);
  const [versions, setVersions] = useState([]);
  const [configs, setConfigs] = useState([]);
  const [system, setSystem] = useState(null);
  const [loadingSetup, setLoadingSetup] = useState(true);
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
  const [productScopes, setProductScopes] = useState([]);

  useEffect(() => {
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
        const returns = data.find((item) => item.kind === "returns");
        const products = data.find((item) => item.kind === "products");
        const activeConfig = connections.find(
          (item) => item.active_version,
        )?.active_version;
        setForm((current) => ({
          ...current,
          dataset_version_id: current.dataset_version_id || returns?.version_id || "",
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
      .catch((error) => notify(error.message, "error"))
      .finally(() => setLoadingSetup(false));
  }, [notify]);

  useEffect(() => {
    if (!form.product_version_id) {
      setProductScopes([]);
      return;
    }
    api
      .productScopes(form.product_version_id)
      .then(setProductScopes)
      .catch((error) => notify(error.message, "error"));
  }, [form.product_version_id, notify]);

  useEffect(() => {
    onDraftChange?.({ form, step, resumePreflight: step === 3 });
  }, [form, onDraftChange, step]);

  const returns = versions.filter((item) => item.kind === "returns");
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

  const runPreflight = useCallback(async () => {
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
      setDataQuality(quality);
      setPreflight({ status: "ready", data, error: "" });
      setSegmentOrder(data.segments.map((segment) => segment.segment_key));
      setUnresolvedPolicy(data.blocked_count > 0 ? "" : "block_all");
    } catch (error) {
      const message =
        error.status === 405
          ? "当前运行服务未加载任务预检能力，请重启服务后重试（PF-405）。"
          : error.message;
      setPreflight({ status: "error", data: null, error: message });
    }
  }, [configs, form]);

  useEffect(() => {
    if (step === 3) runPreflight();
  }, [runPreflight, step]);

  const updateModelPolicy = (changes) =>
    setForm({ ...form, model_policy: { ...modelPolicy, ...changes } });
  const selectConnection = (configId) => {
    const next = publishedConfigs.find((item) => item.id === configId);
    if (!next) return;
    setForm((current) => ({
      ...current,
      config_version_id: configId,
      model_policy: {
        ...current.model_policy,
        connection_id: next.connection_id,
        cheap_audit_percent: next.cheap_audit_percent ?? 5,
      },
    }));
  };
  const selectedReturns = returns.find(
    (item) => item.version_id === form.dataset_version_id,
  );
  const selectedProducts = products.find(
    (item) => item.version_id === form.product_version_id,
  );
  const ready =
    returns.length > 0 && products.length > 0 && publishedConfigs.length > 0;
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
    try {
      await api.createTask({
        ...form,
        store: null,
        listing: null,
        title: form.title || `${selectedReturns?.dataset_name || "退货明细"} 语义分析`,
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
        setPreflight({
          status: "error",
          data: null,
          error: "执行计划已变化，请重新预检后再启动任务。",
        });
        setUnresolvedPolicy("");
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
    onDraftChange?.({ form, step: 3, resumePreflight: true });
    onNavigate("data", {
      kind: "dataset",
      id: productVersion?.dataset_id,
      datasetKind: "products",
      returnToTask: true,
      taskTitle:
        form.title || `${selectedReturns?.dataset_name || "退货明细"} 语义分析`,
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
      setPreflight({ status: "idle", data: null, error: "" });
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

  const creationStage = step === 1 ? 1 : preflight.status === "ready" ? 3 : 2;
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
            : "确认计划并启动";

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
        eyebrow="创建分析任务"
        title={step === 3 ? "确认执行计划" : "创建退货语义分析任务"}
        description={
          step === 3
            ? "系统已按商品品类拆分任务；确认排除与阻断规则后即可执行。"
            : "导入或选择退货明细并设置模型策略，系统会自动完成商品匹配并生成执行计划。"
        }
      />
      <nav className="task-create-progress" aria-label="任务创建步骤">
        {[
          ["配置任务", "导入退货明细与设置模型策略"],
          ["商品匹配与检查", "确认匹配范围与异常处理"],
          ["确认并启动", "创建后进入运行监控"],
        ].map(([label, note], index) => {
          const stage = index + 1;
          const stepState =
            stage < creationStage
              ? "已完成"
              : stage === creationStage
                ? "当前步骤"
                : "未开始";
          return (
            <div
              className={classNames(
                stage === creationStage && "active",
                stage < creationStage && "complete",
              )}
              key={label}
              role="group"
              aria-label={`${label}，${stepState}`}
              aria-current={stage === creationStage ? "step" : undefined}
            >
              <span aria-hidden="true">
                {stage < creationStage ? <Check size={14} /> : stage}
              </span>
              <b>{label}</b>
              <small>{note}</small>
            </div>
          );
        })}
      </nav>
      {loadingSetup && (
        <section className="new-task-loading">
          <InlineLoading label="正在读取数据与模型配置…" />
        </section>
      )}
      {!loadingSetup && !ready && (
        <SetupBlock
          onNavigate={onNavigate}
          onUploadReturns={() => setUploadOpen(true)}
          hasReturns={returns.length > 0}
          hasProducts={products.length > 0}
          hasConfig={publishedConfigs.length > 0}
        />
      )}
      {!loadingSetup && ready && step !== 3 && (
        <TaskConfigurationStep
          form={form}
          onFormChange={setForm}
          returns={returns}
          selectedReturns={selectedReturns}
          selectedProducts={selectedProducts}
          onUploadReturns={() => setUploadOpen(true)}
          publishedConfigs={publishedConfigs}
          selectedConfig={selectedConfig}
          availableModels={availableModels}
          modelPolicy={modelPolicy}
          onConnectionChange={selectConnection}
          onModelPolicyChange={updateModelPolicy}
          system={system}
          onGeneratePlan={() => setStep(3)}
        />
      )}
      {!loadingSetup && ready && step === 3 && (
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
          form={form}
          selectedReturns={selectedReturns}
          modelPolicy={modelPolicy}
          system={system}
          requiresScopeConfirmation={requiresScopeConfirmation}
          scopeConfirmed={scopeConfirmed}
          onScopeConfirmationChange={setScopeConfirmed}
          submitting={submitting}
          submitLabel={submitLabel}
          onSubmit={submit}
          onBack={() => setStep(1)}
        />
      )}
      {uploadOpen && (
        <DatasetUploadDialog
          dialog={
            selectedReturns?.dataset_id
              ? {
                  mode: "version",
                  dataset: {
                    id: selectedReturns.dataset_id,
                    name: selectedReturns.dataset_name,
                    kind: "returns",
                  },
                }
              : { mode: "create", kind: "returns" }
          }
          storeOptions={productScopes.map((scope) => scope.store)}
          onClose={() => setUploadOpen(false)}
          onDone={async (dataset) => {
            const data = await api.dataVersions();
            const uploaded = data.find(
              (item) => item.kind === "returns" && item.dataset_id === dataset.id,
            );
            setVersions(data);
            setForm((current) => ({
              ...current,
              dataset_version_id: uploaded?.version_id ?? current.dataset_version_id,
            }));
            setUploadOpen(false);
            onChanged();
            notify("新版本已上传并自动选中");
          }}
        />
      )}
    </div>
  );
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
