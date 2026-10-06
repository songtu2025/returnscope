/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDraft} ClassificationStandardDraft */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationSource} ClassificationStandardValidationSource */
/** @typedef {import("../../shared/api/classificationStandardContracts").ValidationComparisonType} ValidationComparisonType */
/** @typedef {import("../../shared/api/classificationStandardContracts").ValidationSampleSize} ValidationSampleSize */

/** @typedef {Pick<import("./ClassificationStandardValidationLauncher").ClassificationStandardValidationLauncherProps, "sources" | "sourceId" | "sampleSize" | "onSourceChange" | "onSampleSizeChange"> & {comparisonType: ValidationComparisonType, setComparisonType: (value: ValidationComparisonType) => void}} SampleConfigurationProps */
/** @type {ValidationSampleSize[]} */
const SAMPLE_SIZES = [20, 50, 100];
/** @param {SampleConfigurationProps} props */
function ValidationPurpose({ comparisonType, setComparisonType }) {
  return (
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
  );
}
/** @param {SampleConfigurationProps} props */
function ValidationSource({ sources, sourceId, onSourceChange }) {
  return (
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
  );
}
/** @param {SampleConfigurationProps} props */
function ValidationSampleSize({ sampleSize, onSampleSizeChange }) {
  return (
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
  );
}
/** @param {SampleConfigurationProps} props */
export function ValidationSampleConfiguration(props) {
  return (
    <div className="standard-validation-configuration">
      <ValidationPurpose {...props} />
      <ValidationSource {...props} />
      <ValidationSampleSize {...props} />
    </div>
  );
}
