import {
  CheckCircle,
  Flask,
  Play,
  SpinnerGap,
  WarningCircle,
} from "@phosphor-icons/react";
import { useState } from "react";

const STATUS_LABELS = {
  queued: "等待运行",
  running: "正在分类",
  completed: "验证完成",
  failed: "验证失败",
};

const SAMPLE_SIZES = [20, 50, 100];

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
  const [reviewFile, setReviewFile] = useState(null);
  const [comparisonType, setComparisonType] = useState("standard_version");
  const reviewMode = sourceId === "__review_file__" || !sourceId;
  const active = runs.some((run) => ["queued", "running"].includes(run.status));
  return (
    <div className="standard-sample-validation">
      <section className="standard-validation-launcher">
        <header>
          <div>
            <p className="eyebrow">发布前验证</p>
            <h3>用真实评论检验草稿分类效果</h3>
            <p>
              选择退货数据，或上传当前品类的 Review
              表格。旧版与草稿使用同一批样本对比；验证不会生成正式分类结果。
            </p>
          </div>
          <Flask size={24} />
        </header>
        {dirty && (
          <div className="standard-validation-notice warning">
            当前有未保存修改，开始验证时会先保存并生成新的草稿修订。
          </div>
        )}
        {draft.validation.blocking.length > 0 && (
          <div className="standard-validation-notice blocking">
            请先解决结构检查中的阻断项，再运行样本验证。
          </div>
        )}
        {
          <div className="standard-validation-controls">
            <label>
              验证目的
              <select
                aria-label="验证目的"
                value={comparisonType}
                onChange={(event) => setComparisonType(event.target.value)}
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
                  <option
                    key={source.result_version_id}
                    value={source.result_version_id}
                  >
                    {source.source_kind === "raw_dataset"
                      ? `${source.return_dataset_name} V${source.version_no} · ${source.product_dataset_name}`
                      : `${source.listing || "未指定 Listing"} · 结果 V${source.version_no} · 可抽样 ${source.available_sample_count} 条`}
                  </option>
                ))}
              </select>
            </label>
            {reviewMode && (
              <label>
                Review 表格
                <input
                  type="file"
                  accept=".xlsx"
                  aria-label="Review 表格"
                  onChange={(event) => setReviewFile(event.target.files?.[0] ?? null)}
                />
                <small>
                  需包含评论内容列，可含评论标题、评论编号、一级品类、ASIN；无品类列时按当前标准验证。
                </small>
                <details>
                  <summary>导入人工参考答案（可选）</summary>
                  <small>
                    同一文件可增加“人工参考答案”工作表，列为评论编号、标签编码、评价方向、部位、证据；多标签逐行填写，无标签填写“无标签”。可用“存在歧义”列标记“是”，排除不确定答案。参考答案只用于评分，不发送给模型。
                  </small>
                </details>
              </label>
            )}
            <div>
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
            <button
              type="button"
              className="primary-button"
              disabled={
                busy ||
                active ||
                (reviewMode ? !reviewFile : !sourceId) ||
                draft.validation.blocking.length > 0
              }
              onClick={() => onRun(reviewMode ? reviewFile : null, comparisonType)}
            >
              {busy ? <SpinnerGap size={16} className="spin" /> : <Play size={16} />}
              {busy ? "正在创建" : "开始样本验证"}
            </button>
          </div>
        }
      </section>

      <section className="standard-validation-history">
        <header>
          <div>
            <h3>验证记录</h3>
            <p>验证绑定草稿修订；草稿再次保存后，旧结果自动失效。</p>
          </div>
          <span>{runs.length} 次</span>
        </header>
        {runs.length === 0 ? (
          <div className="standard-validation-empty-source">尚未运行样本验证。</div>
        ) : (
          <div className="standard-validation-run-list">
            {runs.map((run) => (
              <button
                type="button"
                key={run.id}
                className={selectedRun?.id === run.id ? "active" : ""}
                onClick={() => onSelectRun(run.id)}
              >
                <span className={`standard-run-status ${run.status}`}>
                  {run.status === "completed" ? (
                    <CheckCircle size={16} weight="fill" />
                  ) : run.status === "failed" ? (
                    <WarningCircle size={16} weight="fill" />
                  ) : (
                    <SpinnerGap size={16} className="spin" />
                  )}
                  {STATUS_LABELS[run.status]}
                </span>
                <span>草稿 r{run.draft_revision}</span>
                <span>
                  {run.processed_count}/{run.sample_size} 条
                </span>
                <span>{run.is_current ? "当前修订" : "已失效"}</span>
              </button>
            ))}
          </div>
        )}
      </section>

      {selectedRun && (
        <ValidationResult
          key={selectedRun.id}
          run={selectedRun}
          isNew={draft.is_new}
          approvalBusy={approvalBusy}
          onApprove={onApprove}
        />
      )}
    </div>
  );
}

function ValidationResult({ run, isNew, approvalBusy, onApprove }) {
  const [filter, setFilter] = useState("all");
  if (["queued", "running"].includes(run.status)) {
    const percent = run.sample_size
      ? Math.round((run.processed_count / run.sample_size) * 100)
      : 0;
    return (
      <section className="standard-validation-runtime" role="status">
        <SpinnerGap size={19} className="spin" />
        <div>
          <b>
            {run.stage === "comparing_baseline"
              ? "正在验证旧版标准"
              : STATUS_LABELS[run.status]}
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
        <WarningCircle size={19} weight="fill" />
        <div>
          <b>样本验证失败</b>
          <span>{run.error || "模型调用未完成，请重新运行。"}</span>
        </div>
      </section>
    );
  }
  const summary = run.summary;
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
      {run.source.skipped_category_count > 0 && (
        <p>已排除 {run.source.skipped_category_count} 条不属于当前品类的评论。</p>
      )}
      {summary.reference_evaluation?.sample_count > 0 && (
        <section>
          <h3>人工参考答案对比 · {summary.reference_evaluation.sample_count} 条</h3>
          <p>
            排除歧义样本 {summary.reference_evaluation.ambiguous_count}{" "}
            条；发布验证仅对草稿评分，避免新旧编码不同造成误判。证据是否充分仍需人工审阅。
          </p>
          <table>
            <thead>
              <tr>
                <th>结果</th>
                <th>多标</th>
                <th>漏标</th>
                <th>方向错误</th>
                <th>明确部位漏错</th>
                <th>标签完全一致</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(summary.reference_evaluation.sides).map(
                ([side, values]) => (
                  <tr key={side}>
                    <td>{side === "baseline" ? "对照" : "候选"}</td>
                    <td>{values.extra_labels}</td>
                    <td>{values.missing_labels}</td>
                    <td>{values.direction_errors}</td>
                    <td>{values.part_errors}</td>
                    <td>{values.exact_label_samples}</td>
                  </tr>
                ),
              )}
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
          onChange={(event) => setFilter(event.target.value)}
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
              (filter === "unknown" && item.draft.unknown_semantics?.length > 0),
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
              <span>{semanticLabels(item.draft)}</span>
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
      <ValidationApproval
        run={run}
        isNew={isNew}
        busy={approvalBusy}
        onApprove={onApprove}
      />
    </section>
  );
}

function ValidationApproval({ run, isNew, busy, onApprove }) {
  const [confirmed, setConfirmed] = useState(false);
  const [note, setNote] = useState("");
  if (run.approved_at) {
    return (
      <div className="standard-validation-approval ready">
        <CheckCircle size={20} weight="fill" />
        <div>
          <b>{isNew ? "验证结果已人工确认" : "验证差异已人工确认"}</b>
          <span>
            {run.approved_by_name || "当前用户"}：{run.approval_note}
          </span>
        </div>
      </div>
    );
  }
  if (
    !run.is_current ||
    Number(run.error_count) > 0 ||
    (run.source.comparison_type && run.source.comparison_type !== "standard_version")
  )
    return null;
  return (
    <div className="standard-validation-approval">
      <div>
        <b>人工审阅确认</b>
        <span>
          请检查{isNew ? "样本分类" : "标签变化"}
          、覆盖率、未知语义和评论证据，再确认本次验证。
        </span>
      </div>
      <label className="standard-validation-confirmation">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(event) => setConfirmed(event.target.checked)}
        />
        {isNew ? "我已审阅样本分类和证据" : "我已审阅新旧版本差异和样本证据"}
      </label>
      <label>
        验证结论
        <textarea
          rows={2}
          value={note}
          placeholder="例如：新增标签边界清楚，未知语义均已检查"
          onChange={(event) => setNote(event.target.value)}
        />
      </label>
      <button
        type="button"
        className="primary-button"
        disabled={busy || !confirmed || !note.trim()}
        onClick={() => onApprove(run.id, note.trim())}
      >
        {busy ? <SpinnerGap size={16} className="spin" /> : <CheckCircle size={16} />}
        {busy ? "确认中" : "确认验证通过"}
      </button>
    </div>
  );
}

function Metric({ label, value, note }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

function labels(values) {
  return values?.length ? values.join("、") : "无标签";
}

function semanticLabels(result) {
  if (!result.semantic_units?.length) return labels(result.primary_label_codes);
  return result.semantic_units.map((unit, index) => (
    <span
      key={`${unit.label_code}-${index}`}
      style={{ display: "block", overflowWrap: "anywhere" }}
    >
      {{ POSITIVE: "正向", NEGATIVE: "负向", NEUTRAL: "中性" }[unit.sentiment] || ""}
      {" · "}
      {unit.label_code}
      {unit.opinion && <small>{unit.opinion}</small>}
    </span>
  ));
}
