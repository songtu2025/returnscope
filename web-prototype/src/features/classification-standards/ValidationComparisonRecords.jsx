import { CLASSIFICATION_LABEL_SENTIMENTS as SENTIMENT_LABELS } from "./classificationLabelSentiments";
import { ValidationFactTrace } from "./ClassificationValidationQuality";
/** @typedef {import("./ClassificationStandardValidationResult").ClassificationStandardValidationResultProps} ResultProps */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationRunDetail} ClassificationStandardValidationRunDetail */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationValidationSemanticResult} ClassificationValidationSemanticResult */
/** @typedef {ClassificationStandardValidationRunDetail["items"][number]} ComparisonItem */
/** @typedef {"all" | "changed" | "semantic" | "primary" | "errors" | "unknown"} ComparisonFilter */

/** @param {string[] | undefined} values */
function labels(values) {
  return values?.length ? values.join("、") : "无标签";
}

/** @param {ClassificationValidationSemanticResult} result */
function semanticLabels(result) {
  if (!result.semantic_units?.length) return labels(result.primary_label_codes);
  return result.semantic_units.map((unit, index) => (
    <span
      key={`${unit.label_code}-${index}`}
      style={{ display: "block", overflowWrap: "anywhere" }}
    >
      {SENTIMENT_LABELS[unit.sentiment] || ""}
      {" · "}
      {unit.label_code}
      {unit.opinion && <small>{unit.opinion}</small>}
    </span>
  ));
}
/** @param {ComparisonItem} item @param {string} filter */
function matchesFilter(item, filter) {
  switch (filter) {
    case "all":
      return true;
    case "changed":
      return item.changed;
    case "semantic":
      return item.semantic_changed;
    case "primary":
      return item.primary_changed;
    case "errors":
      return [item.baseline.status, item.draft.status].includes("MODEL_ERROR");
    case "unknown":
      return (item.draft.unknown_semantics?.length ?? 0) > 0;
    default:
      return false;
  }
}
/** @param {{item: ComparisonItem, hasChangeBreakdown: boolean}} props */
function ComparisonComment({ item, hasChangeBreakdown }) {
  return (
    <span>
      <b>{item.comment}</b>
      <small>
        {item.category_a || "未分类"} / {item.category_b || "未分类"}
      </small>
      {hasChangeBreakdown && item.changed && (
        <small>
          变化：
          {[item.semantic_changed ? "语义结果" : "", item.primary_changed ? "主因" : ""]
            .filter(Boolean)
            .join("、")}
        </small>
      )}
    </span>
  );
}
/** @param {{item: ComparisonItem, isNew: boolean}} props */
function BaselineResult({ item, isNew }) {
  return (
    <>
      {isNew ? (
        <span>{item.baseline.reason || "未填写"}</span>
      ) : (
        <span>
          {semanticLabels(item.baseline)}
          <details>
            <summary>对照证据与状态</summary>
            <small>{item.baseline.status}</small>
            <small>
              {item.baseline.semantic_units?.map((unit) => unit.evidence).join("；") ||
                "无证据"}
            </small>
            {item.baseline.review_reasons?.length > 0 && (
              <small>复核原因：{item.baseline.review_reasons.join("；")}</small>
            )}
          </details>
          {item.baseline.status === "MODEL_ERROR" && (
            <small>
              对照调用失败：
              {item.baseline.review_reasons?.join("；") || "请重新验证"}
            </small>
          )}
        </span>
      )}
    </>
  );
}
/** @param {{item: ComparisonItem}} props */
function DraftEvidence({ item }) {
  return (
    <span>
      <b>{item.draft.status}</b>
      <small>
        {item.draft.semantic_units.map((unit) => unit.evidence).join("；") || "无证据"}
      </small>
      {item.draft.review_reasons.length > 0 && (
        <small>复核原因：{item.draft.review_reasons.join("；")}</small>
      )}
    </span>
  );
}
/** @param {{item: ComparisonItem, isNew: boolean, hasChangeBreakdown: boolean}} props */
function ComparisonRow({ item, isNew, hasChangeBreakdown }) {
  return (
    <div className={item.changed ? "changed" : ""}>
      <ComparisonComment item={item} hasChangeBreakdown={hasChangeBreakdown} />
      <BaselineResult item={item} isNew={isNew} />
      <span>
        {semanticLabels(item.draft)}
        <ValidationFactTrace result={item.draft} />
      </span>
      <DraftEvidence item={item} />
    </div>
  );
}
/** @param {{run: ClassificationStandardValidationRunDetail, isNew: boolean, hasChangeBreakdown: boolean, filter: ComparisonFilter}} props */
export function ValidationComparisonRecords({
  run,
  isNew,
  hasChangeBreakdown,
  filter,
}) {
  return (
    <div className="standard-validation-comparison">
      <div className="standard-validation-comparison-head">
        <span>评论与品类</span>
        <span>{isNew ? "原始退货原因" : "对照结果"}</span>
        <span>候选结果</span>
        <span>证据与状态</span>
      </div>
      {(run.items || [])
        .filter((item) => matchesFilter(item, filter))
        .map((item) => (
          <ComparisonRow
            key={item.classification_key}
            item={item}
            isNew={isNew}
            hasChangeBreakdown={hasChangeBreakdown}
          />
        ))}
    </div>
  );
}

/** @param {{filter: ComparisonFilter, setFilter: (value: ComparisonFilter) => void, hasChangeBreakdown: boolean}} props */
export function ValidationResultFilter({ filter, setFilter, hasChangeBreakdown }) {
  return (
    <label>
      结果筛选
      <select
        aria-label="验证结果筛选"
        value={filter}
        onChange={(event) =>
          setFilter(
            /** @type {"all" | "changed" | "semantic" | "primary" | "errors" | "unknown"} */ (
              event.target.value
            ),
          )
        }
      >
        <option value="all">全部结果</option>
        <option value="changed">任一结果变化</option>
        {hasChangeBreakdown && <option value="semantic">语义结果变化</option>}
        {hasChangeBreakdown && <option value="primary">主因变化</option>}
        <option value="errors">模型错误</option>
        <option value="unknown">未知语义</option>
      </select>
    </label>
  );
}
