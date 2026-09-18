import { WarningCircle } from "@phosphor-icons/react";
import Button from "antd/es/button";

import { InlineLoading, PageHeading } from "../../components/SharedUi";
import { SetupBlock } from "./NewTaskActions";
import { ReturnImportDialog } from "./ReturnImportDialog";
import { TaskConfigurationStep } from "./TaskConfigurationStep";
import { TaskDataStep } from "./TaskDataStep";
import { TaskPlanReviewStep } from "./TaskPlanReviewStep";

/** @typedef {import("./taskCreateContracts").ApiConnection} ApiConnection */
/** @typedef {import("./taskCreateContracts").AvailableModel} AvailableModel */
/** @typedef {import("./taskCreateContracts").DataVersion} DataVersion */
/** @typedef {import("./taskCreateContracts").MysqlFormState} MysqlFormState */
/** @typedef {import("./taskCreateContracts").PublishedConfig} PublishedConfig */
/** @typedef {import("./taskCreateContracts").ReturnImportResult} ReturnImportResult */
/** @typedef {import("./taskCreateContracts").TaskForm} TaskForm */
/** @typedef {import("./taskCreateContracts").TaskModelPolicy} TaskModelPolicy */
/** @typedef {import("./taskCreateContracts").TaskPlanViewState} TaskPlanViewState */
/** @typedef {import("./taskCreateContracts").TaskPreflightState} TaskPreflightState */
/** @typedef {import("./MysqlReturnImportForm").MysqlReturnFormState} MysqlReturnFormState */
/** @typedef {import("../task-planning/taskPlanContracts").TaskDataQuality} TaskDataQuality */
/** @typedef {import("../task-planning/taskPlanContracts").TaskPlanCounts} TaskPlanCounts */
/**
 * @typedef {Object} NewTaskViewProps
 * @property {import("react").RefObject<HTMLHeadingElement | null>} headingRef
 * @property {{loading: boolean, error: string, ready: boolean, onRetry: () => void, onNavigate: import("../../app/navigation").Navigate, returns: DataVersion[], products: DataVersion[], publishedConfigs: PublishedConfig[]}} setup
 * @property {{form: TaskForm, updateForm: (form: TaskForm) => void, selectedReturns?: DataVersion, dataEntryMode: "mysql" | "upload" | "existing", selectedDataLabel: string, onDataEntryModeChange: (mode: "mysql" | "upload" | "existing") => void, setSelectedDataLabel: import("react").Dispatch<import("react").SetStateAction<string>>, mysqlDraft?: Partial<MysqlReturnFormState>, setMysqlDraft: import("react").Dispatch<import("react").SetStateAction<Partial<MysqlReturnFormState> | undefined>>, setMysqlState: import("react").Dispatch<import("react").SetStateAction<MysqlFormState>>, mysqlState: MysqlFormState, prepared: boolean, scopeLabel: string, onInvalidateMysql: () => void}} data
 * @property {{preflight: TaskPreflightState, runPreflight: () => void | Promise<void>, state: TaskPlanViewState, counts: TaskPlanCounts, dataQuality: TaskDataQuality | null, unresolvedPolicy: string, onPolicyChange: (policy: string) => void, resolveCategories: () => void, segmentOrder: string[], setSegmentOrder: import("react").Dispatch<import("react").SetStateAction<string[]>>, scopeConfirmed: boolean, setScopeConfirmed: import("react").Dispatch<import("react").SetStateAction<boolean>>}} plan
 * @property {{confirmationRef: import("react").RefObject<HTMLHeadingElement | null>, selectedConfig?: PublishedConfig, availableModels: AvailableModel[], modelPolicy: TaskModelPolicy, selectConnection: (configId: string) => void, updateModelPolicy: (changes: Record<string, string | number>) => void, submitError: string, submitting: boolean}} configuration
 * @property {{open: boolean, onOpen: () => void, onClose: () => void, onDone: (result: ReturnImportResult, source: "mysql" | "upload") => void | Promise<void>}} upload
 * @property {import("react").ReactNode} taskActions
 */

/** @param {NewTaskViewProps} props */
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
        description="选择用户反馈数据，准备好后开始分析。"
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
