/** @typedef {import("./ClassificationStandardValidationResult").ClassificationStandardValidationResultProps} ResultProps */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationRunDetail} ClassificationStandardValidationRunDetail */
/** @typedef {NonNullable<ClassificationStandardValidationRunDetail["summary"]["reference_evaluation"]>} ReferenceEvaluation */
/** @param {{side: string, values: ReferenceEvaluation["sides"][string]}} props */
function ReferenceRow({ side, values }) {
  return (
    <tr>
      <td>{side === "baseline" ? "对照" : "候选"}</td>
      <td>{values.duplicate_units ?? 0}</td>
      <td>{values.extra_labels}</td>
      <td>{values.missing_labels}</td>
      <td>{values.direction_errors}</td>
      <td>{values.part_errors}</td>
      <td>{values.evidence_errors ?? 0}</td>
      <td>{values.exact_label_samples}</td>
    </tr>
  );
}
/** @param {{referenceEvaluation: ReferenceEvaluation | null | undefined}} props */
export function ValidationReferenceComparison({ referenceEvaluation }) {
  return (
    <>
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
                <ReferenceRow key={side} side={side} values={values} />
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}
