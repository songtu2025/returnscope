import { useState } from "react";
import { SpinnerGap, WarningCircle } from "@phosphor-icons/react";

import {
  ClassificationValidationQuality,
  ValidationFactTrace,
} from "./ClassificationValidationQuality";
import { ClassificationStandardValidationApproval } from "./ClassificationStandardValidationApproval";

/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardSentiment} ClassificationStandardSentiment */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationRunDetail} ClassificationStandardValidationRunDetail */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationValidationSemanticResult} ClassificationValidationSemanticResult */
/** @typedef {{run: ClassificationStandardValidationRunDetail, isNew: boolean, approvalBusy: boolean, statusLabels: Record<string, string>, onApprove: (runId: string, note: string) => void}} ClassificationStandardValidationResultProps */

/** @type {Record<ClassificationStandardSentiment, string>} */
const SENTIMENT_LABELS = {
  POSITIVE: "正向",
  NEGATIVE: "负向",
  NEUTRAL: "中性",
};

/** @param {ClassificationStandardValidationResultProps} props */
export function ClassificationStandardValidationResult({
  run,
  isNew,
  approvalBusy,
  statusLabels,
  onApprove,
}) {
  const [filter, setFilter] = useState(
    /** @type {"all" | "changed" | "errors" | "unknown"} */ ("all"),
  );
  if (["queued", "running"].includes(run.status)) {
    const percent = run.sample_size
      ? Math.round((run.processed_count / run.sample_size) * 100)
      : 0;
    return (
      <section className="standard-validation-runtime" role="status">
        <SpinnerGap size={19} className="spin" aria-hidden="true" />
        <div>
          <b>
            {run.stage === "comparing_baseline"
              ? "正在验证旧版标准"
              : statusLabels[run.status]}
          </b>
          <span>
            {run.stage === "comparing_baseline" ? "旧版" : "草稿"}已处理{" "}
            {run.processed_count}/{run.sample_size} 条
          </span>
          <div>
            <i style={{ width: `${percent}%` }} />
          </div>
        </div>
      </section>
    );
  }
  if (run.status === "failed") {
    return (
      <section className="standard-validation-runtime failed" role="alert">
        <WarningCircle size={19} weight="fill" aria-hidden="true" />
        <div>
          <b>样本验证失败</b>
          <span>{run.error || "模型调用未完成，请重新运行。"}</span>
        </div>
      </section>
    );
  }
  const summary = run.summary;
  const referenceEvaluation = summary.reference_evaluation;
  return (
    <section className="standard-validation-result">
      <header>
        <div>
          <h3>草稿 r{run.draft_revision} 验证结果</h3>
          <p>
            {run.source.filename || run.source.listing || "未指定 Listing"} ·{" "}
            {run.source.analysis_context === "review" ? "Review 评价" : "退货反馈"} ·{" "}
            {run.sample_size} 条样本 · {run.model_names.join("、") || "模型未记录"}
          </p>
        </div>
        <span className={run.publication_ready ? "ready" : "stale"}>
          {run.publication_ready
            ? "可用于发布"
            : !run.is_current
              ? "已失效"
              : Number(run.error_count) > 0
                ? "存在模型错误"
                : run.source.comparison_type &&
                    run.source.comparison_type !== "standard_version"
                  ? "诊断完成"
                  : run.quality_gate?.passed === false
                    ? "质量门槛未通过"
                    : "等待人工确认"}
        </span>
      </header>
      {run.source.recognition_contract && (
        <p>
          对照：{run.source.recognition_contract.baseline.profile} →{" "}
          {run.source.recognition_contract.candidate.profile}
          {run.source.comparison_type !== "standard_version" &&
            " · 仅用于诊断，不能代替发布验证"}
        </p>
      )}
      <p>
        以下为模型输出的覆盖与复核情况，不代表人工标注准确率。正负观点均计入标签覆盖。
      </p>
      {(run.source.skipped_category_count ?? 0) > 0 && (
        <p>已排除 {run.source.skipped_category_count} 条不属于当前品类的评论。</p>
      )}
      <ClassificationValidationQuality run={run} />
      {referenceEvaluation && referenceEvaluation.sample_count > 0 && (
        <section>
          <h3>人工参考答案对比 · {referenceEvaluation.sample_count} 条</h3>
          <p>
            排除歧义样本 {referenceEvaluation.ambiguous_count}{" "}
            条；发布验证仅对草稿评分，避免新旧编码不同造成误判。证据是否充分仍需人工审阅。
          </p>
          <table>
            <thead>
              <tr>
                <th>结果</th>
                <th>重复实例</th>
                <th>多标实例</th>
                <th>漏标</th>
                <th>方向错误</th>
                <th>明确部位漏错</th>
                <th>证据检查失败</th>
                <th>实例一致样本</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(referenceEvaluation.sides).map(([side, values]) => (
                <tr key={side}>
                  <td>{side === "baseline" ? "对照" : "候选"}</td>
                  <td>{values.duplicate_units ?? 0}</td>
                  <td>{values.extra_labels}</td>
                  <td>{values.missing_labels}</td>
                  <td>{values.direction_errors}</td>
                  <td>{values.part_errors}</td>
                  <td>{values.evidence_errors ?? 0}</td>
                  <td>{values.exact_label_samples}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <div className="standard-validation-metrics">
        <Metric
          label={isNew ? "有效样本" : "标签变化"}
          value={isNew ? summary.sample_size : `${summary.changed_rate}%`}
          note={isNew ? "条真实评论" : `${summary.changed_count} 条`}
        />
        <Metric
          label="标签覆盖"
          value={`${summary.coverage_rate}%`}
          note={`${summary.coverage_count} 条`}
        />
        <Metric
          label="待审核"
          value={`${summary.review_rate}%`}
          note={`${summary.review_count} 条`}
        />
        <Metric
          label="未知语义"
          value={`${summary.unknown_rate}%`}
          note={`${summary.unknown_count} 条`}
        />
        <Metric
          label="模型错误"
          value={`${summary.error_rate}%`}
          note={`${summary.error_count} 条`}
        />
      </div>
      <label>
        结果筛选
        <select
          aria-label="验证结果筛选"
          value={filter}
          onChange={(event) =>
            setFilter(
              /** @type {"all" | "changed" | "errors" | "unknown"} */ (
                event.target.value
              ),
            )
          }
        >
          <option value="all">全部结果</option>
          <option value="changed">结果不同</option>
          <option value="errors">模型错误</option>
          <option value="unknown">未知语义</option>
        </select>
      </label>
      <div className="standard-validation-comparison">
        <div className="standard-validation-comparison-head">
          <span>评论与品类</span>
          <span>{isNew ? "原始退货原因" : "对照结果"}</span>
          <span>候选结果</span>
          <span>证据与状态</span>
        </div>
        {(run.items || [])
          .filter(
            (item) =>
              filter === "all" ||
              (filter === "changed" && item.changed) ||
              (filter === "errors" &&
                [item.baseline.status, item.draft.status].includes("MODEL_ERROR")) ||
              (filter === "unknown" && (item.draft.unknown_semantics?.length ?? 0) > 0),
          )
          .map((item) => (
            <div
              key={item.classification_key}
              className={item.changed ? "changed" : ""}
            >
              <span>
                <b>{item.comment}</b>
                <small>
                  {item.category_a || "未分类"} / {item.category_b || "未分类"}
                </small>
              </span>
              {isNew ? (
                <span>{item.baseline.reason || "未填写"}</span>
              ) : (
                <span>
                  {semanticLabels(item.baseline)}
                  <details>
                    <summary>对照证据与状态</summary>
                    <small>{item.baseline.status}</small>
                    <small>
                      {item.baseline.semantic_units
                        ?.map((unit) => unit.evidence)
                        .join("；") || "无证据"}
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
              <span>
                {semanticLabels(item.draft)}
                <ValidationFactTrace result={item.draft} />
              </span>
              <span>
                <b>{item.draft.status}</b>
                <small>
                  {item.draft.semantic_units.map((unit) => unit.evidence).join("；") ||
                    "无证据"}
                </small>
                {item.draft.review_reasons.length > 0 && (
                  <small>复核原因：{item.draft.review_reasons.join("；")}</small>
                )}
              </span>
            </div>
          ))}
      </div>
      <ClassificationStandardValidationApproval
        run={run}
        isNew={isNew}
        busy={approvalBusy}
        onApprove={onApprove}
      />
    </section>
  );
}

/** @param {{label: string, value: string | number, note: string}} props */
function Metric({ label, value, note }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

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
