import { ClassificationStandardValidationHistory } from "./ClassificationStandardValidationHistory";
import { ClassificationStandardValidationLauncher } from "./ClassificationStandardValidationLauncher";
import { ClassificationStandardValidationResult } from "./ClassificationStandardValidationResult";

const STATUS_LABELS = {
  queued: "等待运行",
  running: "正在分类",
  completed: "验证完成",
  failed: "验证失败",
};

/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDraft} ClassificationStandardDraft */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationRunDetail} ClassificationStandardValidationRunDetail */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationRunSummary} ClassificationStandardValidationRunSummary */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationSource} ClassificationStandardValidationSource */
/** @typedef {import("../../shared/api/classificationStandardContracts").ValidationSampleSize} ValidationSampleSize */

/**
 * @typedef {object} ClassificationStandardValidationProps
 * @property {ClassificationStandardDraft} draft
 * @property {ClassificationStandardValidationSource[]} sources
 * @property {ClassificationStandardValidationRunSummary[]} runs
 * @property {ClassificationStandardValidationRunDetail | null} selectedRun
 * @property {string} sourceId
 * @property {ValidationSampleSize} sampleSize
 * @property {boolean} busy
 * @property {boolean} approvalBusy
 * @property {boolean} dirty
 * @property {(sourceId: string) => void} onSourceChange
 * @property {(sampleSize: ValidationSampleSize) => void} onSampleSizeChange
 * @property {(file: File | null, comparisonType: string) => void} onRun
 * @property {(runId: string, note: string) => void} onApprove
 * @property {(runId: string) => void} onSelectRun
 */

/** @param {ClassificationStandardValidationProps} props */
export function ClassificationStandardValidation({
  draft,
  sources,
  runs,
  selectedRun,
  sourceId,
  sampleSize,
  busy,
  approvalBusy,
  dirty,
  onSourceChange,
  onSampleSizeChange,
  onRun,
  onApprove,
  onSelectRun,
}) {
  const active = runs.some((run) => ["queued", "running"].includes(run.status));
  return (
    <div className="standard-sample-validation">
      <ClassificationStandardValidationLauncher
        draft={draft}
        sources={sources}
        sourceId={sourceId}
        sampleSize={sampleSize}
        busy={busy}
        active={active}
        dirty={dirty}
        onSourceChange={onSourceChange}
        onSampleSizeChange={onSampleSizeChange}
        onRun={onRun}
      />
      <ClassificationStandardValidationHistory
        runs={runs}
        selectedRun={selectedRun}
        statusLabels={STATUS_LABELS}
        onSelectRun={onSelectRun}
      />
      {selectedRun && (
        <ClassificationStandardValidationResult
          key={selectedRun.id}
          run={selectedRun}
          isNew={draft.is_new}
          approvalBusy={approvalBusy}
          statusLabels={STATUS_LABELS}
          onApprove={onApprove}
        />
      )}
    </div>
  );
}
