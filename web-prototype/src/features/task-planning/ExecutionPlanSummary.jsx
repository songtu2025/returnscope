import { Pulse } from "@phosphor-icons/react";
import { taskPlanCounts } from "./taskPlanPolicy";
import { ExecutionPlanSegments } from "./ExecutionPlanSegments";
import { ExecutionPlanOverview } from "./ExecutionPlanOverview";
import { ExecutionPlanIssues } from "./ExecutionPlanIssues";

/** @typedef {import("./taskPlanContracts").TaskExecutionPlan} TaskExecutionPlan */
/** @typedef {import("./taskPlanContracts").TaskDataQuality} TaskDataQuality */
/**
 * @typedef {Object} ExecutionPlanSummaryProps
 * @property {TaskExecutionPlan} plan
 * @property {TaskDataQuality | null} [quality]
 * @property {string} [policy]
 * @property {(policy: string) => void} [onPolicyChange]
 * @property {() => void} [onResolveCategories]
 * @property {string[]} [segmentOrder]
 * @property {(segmentOrder: string[]) => void} [onSegmentOrderChange]
 * @property {boolean} [compact]
 */

/** @param {ExecutionPlanSummaryProps} props */
export function ExecutionPlanSummary({
  plan,
  quality,
  policy,
  onPolicyChange,
  onResolveCategories,
  segmentOrder,
  onSegmentOrderChange,
  compact = false,
}) {
  const counts = taskPlanCounts(plan);
  const segmentByKey = new Map(
    plan.segments.map((segment) => [segment.segment_key, segment]),
  );
  const orderedKeys = [
    ...(segmentOrder?.filter((key) => segmentByKey.has(key)) ?? []),
    ...plan.segments
      .map((segment) => segment.segment_key)
      .filter((key) => !segmentOrder?.includes(key)),
  ];
  const orderedSegments = orderedKeys.map(
    (key) =>
      /** @type {import("./taskPlanContracts").TaskPlanSegment} */ (
        segmentByKey.get(key)
      ),
  );
  const segmentsView = (
    <ExecutionPlanSegments
      orderedSegments={orderedSegments}
      onSegmentOrderChange={onSegmentOrderChange}
    />
  );
  return (
    <section className="execution-plan" aria-label="真实品类执行计划">
      <ExecutionPlanOverview
        plan={plan}
        quality={quality}
        counts={counts}
        compact={compact}
      />
      {!compact && segmentsView}
      <ExecutionPlanIssues
        plan={plan}
        counts={counts}
        policy={policy}
        onPolicyChange={onPolicyChange}
        onResolveCategories={onResolveCategories}
      />
      {compact && (
        <details className="task-advanced-settings">
          <summary>查看 {orderedSegments.length} 个执行分组及顺序</summary>
          <div className="task-advanced-body">{segmentsView}</div>
        </details>
      )}
    </section>
  );
}

export function PreflightProgress() {
  return (
    <section
      className="preflight-progress"
      aria-label="执行计划生成进度"
      aria-live="polite"
    >
      <div className="preflight-progress-heading">
        <Pulse size={18} />
        <div>
          <b>正在准备执行计划</b>
          <p>正在匹配商品并检查分析范围，不会调用模型。</p>
        </div>
      </div>
    </section>
  );
}
