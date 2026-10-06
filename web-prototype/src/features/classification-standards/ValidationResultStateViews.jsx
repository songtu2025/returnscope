import { SpinnerGap, WarningCircle } from "@phosphor-icons/react";
/** @typedef {import("./ClassificationStandardValidationResult").ClassificationStandardValidationResultProps} ResultProps */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationRunDetail} ClassificationStandardValidationRunDetail */
/** @param {Pick<ResultProps,"run"|"statusLabels">} props */
export function ValidationRunning({ run, statusLabels }) {
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
/** @param {Pick<ResultProps,"run">} props */
export function ValidationFailed({ run }) {
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
