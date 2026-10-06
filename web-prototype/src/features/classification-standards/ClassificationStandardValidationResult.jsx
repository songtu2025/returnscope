import { useState } from "react";
import { ValidationRunning, ValidationFailed } from "./ValidationResultStateViews";
import { ValidationResultHeading } from "./ValidationResultHeading";
import { ValidationReferenceComparison } from "./ValidationReferenceComparison";
import { ValidationMetrics } from "./ValidationMetrics";
import {
  ValidationComparisonRecords,
  ValidationResultFilter,
} from "./ValidationComparisonRecords";

import { ClassificationValidationQuality } from "./ClassificationValidationQuality";

/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationRunDetail} ClassificationStandardValidationRunDetail */
/** @typedef {{run: ClassificationStandardValidationRunDetail, isNew: boolean, statusLabels: Record<string, string>}} ClassificationStandardValidationResultProps */

/** @param {ClassificationStandardValidationResultProps} props */
export function ClassificationStandardValidationResult({ run, isNew, statusLabels }) {
  const [filter, setFilter] = useState(
    /** @type {"all" | "changed" | "semantic" | "primary" | "errors" | "unknown"} */ (
      "all"
    ),
  );
  if (["queued", "running"].includes(run.status))
    return <ValidationRunning run={run} statusLabels={statusLabels} />;
  if (run.status === "failed") return <ValidationFailed run={run} />;
  const summary = run.summary;
  const referenceEvaluation = summary.reference_evaluation;
  const hasChangeBreakdown =
    typeof summary.semantic_changed_count === "number" &&
    typeof summary.primary_changed_count === "number";
  return (
    <section className="standard-validation-result">
      <ValidationResultHeading run={run} />
      <p>
        以下为模型输出的覆盖与复核情况，不代表人工标注准确率。正负观点均计入标签覆盖。
      </p>
      {(run.source.skipped_category_count ?? 0) > 0 && (
        <p>已排除 {run.source.skipped_category_count} 条不属于当前品类的评论。</p>
      )}
      <ClassificationValidationQuality run={run} />
      <ValidationReferenceComparison referenceEvaluation={referenceEvaluation} />
      <ValidationMetrics
        summary={summary}
        isNew={isNew}
        hasChangeBreakdown={hasChangeBreakdown}
      />
      <ValidationResultFilter
        filter={filter}
        setFilter={setFilter}
        hasChangeBreakdown={hasChangeBreakdown}
      />
      <ValidationComparisonRecords
        run={run}
        isNew={isNew}
        hasChangeBreakdown={hasChangeBreakdown}
        filter={filter}
      />
    </section>
  );
}
