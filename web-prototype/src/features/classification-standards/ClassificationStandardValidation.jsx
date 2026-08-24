import {
  CheckCircle,
  Flask,
  Play,
  SpinnerGap,
  WarningCircle,
} from "@phosphor-icons/react";

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
  dirty,
  onSourceChange,
  onSampleSizeChange,
  onRun,
  onSelectRun,
}) {
  const active = runs.some((run) => ["queued", "running"].includes(run.status));
  return (
    <div className="standard-sample-validation">
      <section className="standard-validation-launcher">
        <header>
          <div>
            <p className="eyebrow">发布前验证</p>
            <h3>用真实评论检验草稿分类效果</h3>
            <p>
              {draft.is_new
                ? "从退货数据与产品信息中抽取当前品类评论；本次运行不会生成正式分类结果。"
                : "原结果只作为基线；本次运行不会改写分类结果或复核记录。"}
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
        {sources.length === 0 ? (
          <div className="standard-validation-empty-source">
            {draft.is_new
              ? "请先维护至少一个退货数据版本和一个产品信息版本。"
              : "当前标准版本还没有可复用的分类结果，需先完成一次分析任务。"}
          </div>
        ) : (
          <div className="standard-validation-controls">
            <label>
              样本来源
              <select
                aria-label="样本来源"
                value={sourceId}
                onChange={(event) => onSourceChange(event.target.value)}
              >
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
                busy || active || !sourceId || draft.validation.blocking.length > 0
              }
              onClick={onRun}
            >
              {busy ? <SpinnerGap size={16} className="spin" /> : <Play size={16} />}
              {busy ? "正在创建" : "开始样本验证"}
            </button>
          </div>
        )}
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

      {selectedRun && <ValidationResult run={selectedRun} isNew={draft.is_new} />}
    </div>
  );
}

function ValidationResult({ run, isNew }) {
  if (["queued", "running"].includes(run.status)) {
    const percent = run.sample_size
      ? Math.round((run.processed_count / run.sample_size) * 100)
      : 0;
    return (
      <section className="standard-validation-runtime" role="status">
        <SpinnerGap size={19} className="spin" />
        <div>
          <b>{STATUS_LABELS[run.status]}</b>
          <span>
            已处理 {run.processed_count}/{run.sample_size} 条
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
            {run.source.listing || "未指定 Listing"} · {run.sample_size} 条样本 ·{" "}
            {run.model_names.join("、") || "模型未记录"}
          </p>
        </div>
        <span className={run.publication_ready ? "ready" : "stale"}>
          {run.publication_ready
            ? "可用于发布"
            : run.is_current
              ? "存在模型错误"
              : "已失效"}
        </span>
      </header>
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
      <div className="standard-validation-comparison">
        <div className="standard-validation-comparison-head">
          <span>评论与品类</span>
          <span>{isNew ? "原始退货原因" : "原标签"}</span>
          <span>草稿标签</span>
          <span>证据与状态</span>
        </div>
        {(run.items || []).map((item) => (
          <div key={item.classification_key} className={item.changed ? "changed" : ""}>
            <span>
              <b>{item.comment}</b>
              <small>
                {item.category_a || "未分类"} / {item.category_b || "未分类"}
              </small>
            </span>
            {isNew ? (
              <span>{item.baseline.reason || "未填写"}</span>
            ) : (
              <code>{labels(item.baseline.primary_label_codes)}</code>
            )}
            <code>{labels(item.draft.primary_label_codes)}</code>
            <span>
              <b>{item.draft.status}</b>
              <small>
                {item.draft.semantic_units.map((unit) => unit.evidence).join("；") ||
                  item.draft.review_reasons.join("；") ||
                  "无证据"}
              </small>
            </span>
          </div>
        ))}
      </div>
    </section>
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
