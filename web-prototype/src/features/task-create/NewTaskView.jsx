import { WarningCircle } from "@phosphor-icons/react";
import Button from "antd/es/button";

import { InlineLoading, PageHeading } from "../../components/SharedUi";
import { SetupBlock } from "./NewTaskActions";
import { ReturnImportDialog } from "./ReturnImportDialog";
import { TaskConfigurationStep } from "./TaskConfigurationStep";
import { TaskDataStep } from "./TaskDataStep";
import { TaskPlanReviewStep } from "./TaskPlanReviewStep";

export function NewTaskView({
  headingRef,
  setup,
  data,
  plan,
  configuration,
  upload,
  taskActions,
}) {
  const {
    loading: loadingSetup,
    error: setupError,
    ready,
    onRetry: onRetrySetup,
    onNavigate,
    returns,
    products,
    publishedConfigs,
  } = setup;
  const {
    form,
    updateForm,
    selectedReturns,
    dataEntryMode,
    selectedDataLabel,
    onDataEntryModeChange,
    setSelectedDataLabel,
    mysqlDraft,
    setMysqlDraft,
    setMysqlState,
    mysqlState,
    prepared,
    scopeLabel,
    onInvalidateMysql,
  } = data;
  const {
    preflight,
    runPreflight,
    state: planState,
    counts: planCounts,
    dataQuality,
    unresolvedPolicy,
    onPolicyChange,
    resolveCategories,
    segmentOrder,
    setSegmentOrder,
    scopeConfirmed,
    setScopeConfirmed,
  } = plan;
  const {
    confirmationRef,
    selectedConfig,
    availableModels,
    modelPolicy,
    selectConnection,
    updateModelPolicy,
    submitError,
    submitting,
  } = configuration;
  const {
    open: uploadOpen,
    onOpen: onUploadReturns,
    onClose: onCloseUpload,
    onDone: finishImport,
  } = upload;
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
          <Button className="secondary-button" onClick={onRetrySetup}>
            重新加载
          </Button>
        </section>
      )}
      {!loadingSetup && !setupError && !ready && (
        <SetupBlock
          onNavigate={onNavigate}
          onUploadReturns={onUploadReturns}
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
          onDataEntryModeChange={onDataEntryModeChange}
          onSelectedDataLabelChange={setSelectedDataLabel}
          onUploadReturns={onUploadReturns}
          mysqlDraft={mysqlDraft}
          onMysqlDraftChange={setMysqlDraft}
          onMysqlDone={(result) => finishImport(result, "mysql")}
          onMysqlStateChange={setMysqlState}
          busy={submitting || mysqlState.busy === "import"}
          prepared={prepared}
          scopeLabel={scopeLabel}
          onInvalidateMysql={onInvalidateMysql}
        >
          {prepared && (
            <TaskPlanReviewStep
              preflight={preflight}
              onRetryPreflight={runPreflight}
              categoryCompletionRequired={planState.categoryCompletionRequired}
              blocked={planState.blocked}
              countMismatch={planState.countMismatch}
              noExecutable={planState.noExecutable}
              partialPlan={planState.partialPlan}
              planCounts={planCounts}
              dataQuality={dataQuality}
              unresolvedPolicy={unresolvedPolicy}
              onPolicyChange={onPolicyChange}
              onResolveCategories={resolveCategories}
              segmentOrder={segmentOrder}
              onSegmentOrderChange={setSegmentOrder}
              requiresScopeConfirmation={planState.requiresScopeConfirmation}
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
          onClose={onCloseUpload}
          onDone={(result) => finishImport(result, "upload")}
        />
      )}
    </div>
  );
}
