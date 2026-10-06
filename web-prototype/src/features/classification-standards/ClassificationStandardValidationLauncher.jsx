import { useState } from "react";
import Button from "antd/es/button";
import { Flask, Play, SpinnerGap } from "@phosphor-icons/react";
import { ValidationSampleConfiguration } from "./ValidationSampleConfiguration";
import { ValidationReviewUpload } from "./ValidationReviewUpload";
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDraft} ClassificationStandardDraft */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationSource} ClassificationStandardValidationSource */
/** @typedef {import("../../shared/api/classificationStandardContracts").ValidationComparisonType} ValidationComparisonType */
/** @typedef {import("../../shared/api/classificationStandardContracts").ValidationSampleSize} ValidationSampleSize */
/** @typedef {{draft: ClassificationStandardDraft, sources: ClassificationStandardValidationSource[], sourceId: string, sampleSize: ValidationSampleSize, busy: boolean, active: boolean, dirty: boolean, onSourceChange: (sourceId: string) => void, onSampleSizeChange: (sampleSize: ValidationSampleSize) => void, onRun: (file: File | null, comparisonType: ValidationComparisonType) => void}} ClassificationStandardValidationLauncherProps */

/** @param {Pick<ClassificationStandardValidationLauncherProps, "busy" | "active" | "draft" | "sourceId"> & {reviewMode: boolean, reviewFile: File | null}} props */
function validationRunDisabledReason({
  busy,
  active,
  draft,
  reviewMode,
  reviewFile,
  sourceId,
}) {
  if (busy) return "正在创建验证任务，请稍候。";
  if (active) return "已有样本验证正在运行，请等待完成。";
  if (draft.validation.blocking.length > 0) return "请先解决结构检查中的阻断项。";
  if (reviewMode && !reviewFile) return "请选择 Review 表格后开始验证。";
  if (!reviewMode && !sourceId) return "请选择样本来源后开始验证。";
  return "";
}
/** @param {{runDisabledReason: string, busy: boolean, disabled: boolean, onRun: () => void}} props */
function ValidationActions({ runDisabledReason, busy, disabled, onRun }) {
  return (
    <div className="standard-validation-actions">
      {runDisabledReason && (
        <p id="standard-validation-disabled-reason" role="status">
          {runDisabledReason}
        </p>
      )}
      <Button
        htmlType="button"
        type="primary"
        className="primary-button"
        disabled={disabled}
        aria-describedby={
          runDisabledReason ? "standard-validation-disabled-reason" : undefined
        }
        icon={
          busy ? (
            <SpinnerGap size={16} className="spin" aria-hidden="true" />
          ) : (
            <Play size={16} aria-hidden="true" />
          )
        }
        onClick={onRun}
      >
        {busy ? "正在创建" : "开始样本验证"}
      </Button>
    </div>
  );
}
/** @param {ClassificationStandardValidationLauncherProps} props */
export function ClassificationStandardValidationLauncher({
  draft,
  sources,
  sourceId,
  sampleSize,
  busy,
  active,
  dirty,
  onSourceChange,
  onSampleSizeChange,
  onRun,
}) {
  const [reviewFile, setReviewFile] = useState(/** @type {File | null} */ (null));
  const [comparisonType, setComparisonType] = useState(
    /** @type {ValidationComparisonType} */ ("standard_version"),
  );
  const reviewMode = sourceId === "__review_file__" || !sourceId;
  const runDisabledReason = validationRunDisabledReason({
    draft,
    sourceId,
    busy,
    active,
    reviewMode,
    reviewFile,
  });
  return (
    <section className="standard-validation-launcher">
      <header>
        <div>
          <h3>用真实评论检验草稿分类效果</h3>
          <p>
            选择退货数据，或上传当前品类的 Review
            表格。旧版与草稿使用同一批样本对比；验证不会生成正式分类结果。
          </p>
        </div>
        <Flask size={24} aria-hidden="true" />
      </header>
      {dirty && (
        <div className="standard-validation-notice warning" role="status">
          当前有未保存修改，开始验证时会先保存并生成新的草稿修订。
        </div>
      )}
      {draft.validation.blocking.length > 0 && (
        <div className="standard-validation-notice blocking" role="alert">
          请先解决结构检查中的阻断项，再运行样本验证。
        </div>
      )}

      <div className="standard-validation-controls">
        <ValidationSampleConfiguration
          sources={sources}
          sourceId={sourceId}
          sampleSize={sampleSize}
          onSourceChange={onSourceChange}
          onSampleSizeChange={onSampleSizeChange}
          comparisonType={comparisonType}
          setComparisonType={setComparisonType}
        />
        {reviewMode && (
          <ValidationReviewUpload
            reviewFile={reviewFile}
            setReviewFile={setReviewFile}
          />
        )}
        <ValidationActions
          runDisabledReason={runDisabledReason}
          busy={busy}
          disabled={
            busy ||
            active ||
            (reviewMode ? !reviewFile : !sourceId) ||
            draft.validation.blocking.length > 0
          }
          onRun={() => onRun(reviewMode ? reviewFile : null, comparisonType)}
        />
      </div>
    </section>
  );
}
