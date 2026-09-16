import { useState } from "react";
import Button from "antd/es/button";
import { Flask, Play, SpinnerGap } from "@phosphor-icons/react";

/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDraft} ClassificationStandardDraft */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationSource} ClassificationStandardValidationSource */
/** @typedef {import("../../shared/api/classificationStandardContracts").ValidationComparisonType} ValidationComparisonType */
/** @typedef {import("../../shared/api/classificationStandardContracts").ValidationSampleSize} ValidationSampleSize */
/** @typedef {{draft: ClassificationStandardDraft, sources: ClassificationStandardValidationSource[], sourceId: string, sampleSize: ValidationSampleSize, busy: boolean, active: boolean, dirty: boolean, onSourceChange: (sourceId: string) => void, onSampleSizeChange: (sampleSize: ValidationSampleSize) => void, onRun: (file: File | null, comparisonType: ValidationComparisonType) => void}} ClassificationStandardValidationLauncherProps */

/** @type {ValidationSampleSize[]} */
const SAMPLE_SIZES = [20, 50, 100];

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
  const runDisabledReason = busy
    ? "正在创建验证任务，请稍候。"
    : active
      ? "已有样本验证正在运行，请等待完成。"
      : draft.validation.blocking.length > 0
        ? "请先解决结构检查中的阻断项。"
        : reviewMode && !reviewFile
          ? "请选择 Review 表格后开始验证。"
          : !reviewMode && !sourceId
            ? "请选择样本来源后开始验证。"
            : "";
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
        <div className="standard-validation-configuration">
          <label>
            验证目的
            <select
              aria-label="验证目的"
              value={comparisonType}
              onChange={(event) =>
                setComparisonType(
                  /** @type {ValidationComparisonType} */ (event.target.value),
                )
              }
            >
              <option value="standard_version">发布验证 · 当前标准与草稿</option>
              <option value="keyword_ab">关键词对照 · 同标签，仅移除关键词</option>
              <option value="semantic_ab">语义方案对照 · 定义、边界与证据</option>
            </select>
          </label>
          <label>
            样本来源
            <select
              aria-label="样本来源"
              value={sourceId || "__review_file__"}
              onChange={(event) => onSourceChange(event.target.value)}
            >
              <option value="__review_file__">上传 Review 样本</option>
              {sources.map((source) => (
                <option key={source.result_version_id} value={source.result_version_id}>
                  {"return_dataset_name" in source
                    ? `${source.return_dataset_name} V${source.version_no} · ${source.product_dataset_name}`
                    : `${source.listing || "未指定 Listing"} · 结果 V${source.version_no} · 可抽样 ${source.available_sample_count} 条`}
                </option>
              ))}
            </select>
          </label>
          <div className="standard-validation-sample-size">
            <span>样本规模</span>
            <div className="standard-sample-size" role="group" aria-label="样本规模">
              {SAMPLE_SIZES.map((value) => (
                <button
                  type="button"
                  key={value}
                  className={sampleSize === value ? "active" : ""}
                  aria-pressed={sampleSize === value}
                  onClick={() => onSampleSizeChange(value)}
                >
                  {value} 条
                </button>
              ))}
            </div>
          </div>
        </div>
        {reviewMode && (
          <div className="standard-review-upload">
            <div>
              <label className="secondary-button standard-json-import-button">
                选择 Review Excel
                <input
                  id="standard-validation-review-file"
                  type="file"
                  accept=".xlsx"
                  aria-label="Review 表格"
                  aria-describedby="standard-validation-review-file-help"
                  onChange={(event) => setReviewFile(event.target.files?.[0] ?? null)}
                />
              </label>
              {reviewFile && <span role="status">已选择：{reviewFile.name}</span>}
              <small id="standard-validation-review-file-help">
                需包含评论内容列，可含评论标题、评论编号、一级品类、ASIN；无品类列时按当前标准验证。
              </small>
            </div>
            <details className="standard-review-reference-help">
              <summary>导入人工参考答案（可选）</summary>
              <p>
                同一文件可增加“人工参考答案”工作表，列为评论编号、标签编码、评价方向、部位、证据；多标签逐行填写，无标签填写“无标签”。可用“存在歧义”列标记“是”，排除不确定答案。事实策略还需填写“事实状态”（EXPERIENCE、EVALUATION、RECOMMENDATION、INTENT、PREDICTION、HYPOTHESIS、REPORTED、NEGATED、NOT_TESTED、ADVICE）；无标签行也需事实状态和证据。“使用者”“商品对象”可选，仅明确填写时比较。参考答案只用于评分，不发送给模型。
              </p>
            </details>
          </div>
        )}
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
            disabled={
              busy ||
              active ||
              (reviewMode ? !reviewFile : !sourceId) ||
              draft.validation.blocking.length > 0
            }
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
            onClick={() => onRun(reviewMode ? reviewFile : null, comparisonType)}
          >
            {busy ? "正在创建" : "开始样本验证"}
          </Button>
        </div>
      </div>
    </section>
  );
}
