/** @typedef {import("./ClassificationStandardValidationResult").ClassificationStandardValidationResultProps} ResultProps */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationRunDetail} ClassificationStandardValidationRunDetail */
/** @param {ClassificationStandardValidationRunDetail} run @param {boolean} canAttachToPublication */
function publicationLabel(run, canAttachToPublication) {
  if (canAttachToPublication)
    return run.quality_gate?.passed === false ? "测试完成，需人工判断" : "自动检查通过";
  if (!run.is_current) return "已失效";
  if (Number(run.error_count) > 0) return "存在模型错误";
  if (run.source.comparison_type && run.source.comparison_type !== "standard_version")
    return "诊断完成";
  return "测试记录不可用于验收";
}
/** @param {Pick<ResultProps,"run">} props */
function PublicationStatus({ run }) {
  const canAttachToPublication =
    run.is_current &&
    Number(run.error_count) === 0 &&
    (run.source.comparison_type ?? "standard_version") === "standard_version";
  return (
    <span className={canAttachToPublication ? "ready" : "stale"}>
      {publicationLabel(run, canAttachToPublication)}
    </span>
  );
}
/** @param {Pick<ResultProps,"run">} props */
function ResultMetadata({ run }) {
  return (
    <div>
      <h3>草稿 r{run.draft_revision} 验证结果</h3>
      <p>
        {run.source.filename || run.source.listing || "未指定 Listing"} ·{" "}
        {run.source.analysis_context === "review"
          ? "Review 评价"
          : run.source.analysis_context === "user_feedback"
            ? "用户反馈"
            : "退货反馈"}{" "}
        · {run.sample_size} 条样本 · {run.model_names.join("、") || "模型未记录"}
      </p>
    </div>
  );
}
/** @param {Pick<ResultProps,"run">} props */
export function ValidationResultHeading({ run }) {
  return (
    <>
      <header>
        <ResultMetadata run={run} />
        <PublicationStatus run={run} />
      </header>
      {run.source.recognition_contract && (
        <p>
          对照：{run.source.recognition_contract.baseline.profile} →{" "}
          {run.source.recognition_contract.candidate.profile}
          {run.source.comparison_type !== "standard_version" &&
            " · 仅用于诊断，不能代替发布验证"}
        </p>
      )}
    </>
  );
}
