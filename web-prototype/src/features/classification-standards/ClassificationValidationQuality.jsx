import { classificationValidationQualityGroups } from "./classificationValidationQualityGroups";
import { ValidationQualityGate } from "./ValidationQualityGate";
import { ValidationQualityGroups } from "./ValidationQualityGroups";
export { ValidationFactTrace } from "./ValidationFactTrace";
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationRunDetail} ClassificationStandardValidationRunDetail */
/** @param {{run: ClassificationStandardValidationRunDetail}} props */
export function ClassificationValidationQuality({ run }) {
  const groups = classificationValidationQualityGroups(run);
  return (
    <section className="standard-quality-summary" aria-label="质量门槛与问题分组">
      <h3>质量门槛与问题分组</h3>
      <ValidationQualityGate run={run} />
      <p>各分组按样本计数，可能重叠，不相加计算错误率。</p>
      <ValidationQualityGroups groups={groups} />
    </section>
  );
}
