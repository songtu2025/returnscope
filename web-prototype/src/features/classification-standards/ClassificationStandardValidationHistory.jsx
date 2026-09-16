import { CheckCircle, SpinnerGap, WarningCircle } from "@phosphor-icons/react";

export function ClassificationStandardValidationHistory({
  runs,
  selectedRun,
  statusLabels,
  onSelectRun,
}) {
  return (
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
                  <CheckCircle size={16} weight="fill" aria-hidden="true" />
                ) : run.status === "failed" ? (
                  <WarningCircle size={16} weight="fill" aria-hidden="true" />
                ) : (
                  <SpinnerGap size={16} className="spin" aria-hidden="true" />
                )}
                {statusLabels[run.status]}
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
  );
}
