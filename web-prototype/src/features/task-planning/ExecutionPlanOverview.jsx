import { CheckCircle, Database, WarningCircle } from "@phosphor-icons/react";
import { classNames } from "../../lib/presentation";

/** @typedef {import("./taskPlanContracts").TaskExecutionPlan} TaskExecutionPlan */
/** @typedef {import("./taskPlanContracts").TaskDataQuality} TaskDataQuality */
/** @typedef {import("./taskPlanContracts").TaskPlanCounts} TaskPlanCounts */
/** @typedef {{plan: TaskExecutionPlan, quality?: TaskDataQuality | null, counts: TaskPlanCounts, compact: boolean}} PlanOverviewProps */

/** @param {PlanOverviewProps} props */
export function ExecutionPlanOverview({ plan, quality, counts, compact }) {
  const qualityCounts = quality?.counts ?? {};
  const qualityTotal = Number(qualityCounts.total_records || 0);
  const qualityMatched = Number(qualityCounts.matched_records || 0);
  const matchRate = qualityTotal > 0 ? (qualityMatched / qualityTotal) * 100 : 0;
  return (
    <>
      <TaskPlanScopeSummary plan={plan} compact={compact} />
      <TaskPlanCountsSummary
        plan={plan}
        counts={counts}
        compact={compact}
        qualityCounts={qualityCounts}
        matchRate={matchRate}
      />
      {(!compact || !counts.reconciled) && (
        <TaskPlanReconciliation plan={plan} counts={counts} />
      )}
    </>
  );
}

/** @param {Pick<PlanOverviewProps, "plan" | "compact">} props */
function TaskPlanScopeSummary({ plan, compact }) {
  const detectedStores = new Set(
    (plan.detected_scopes ?? []).map((scope) => scope.store).filter(Boolean),
  );
  const detectedListings = new Set(
    (plan.detected_scopes ?? []).map((scope) => scope.listing).filter(Boolean),
  );
  return (
    <div className="plan-scope-summary">
      <Database size={20} />
      <div>
        <b>
          系统已识别 {detectedStores.size} 个店铺、{detectedListings.size} 个 Listing
        </b>
        {!compact && (
          <p>
            {plan.primary_store ? `主要站点 ${plan.primary_store}；` : ""}
            范围来自用户反馈数据与系统产品信息的确定性匹配。
          </p>
        )}
      </div>
    </div>
  );
}

/** @param {Pick<PlanOverviewProps, "plan" | "counts" | "compact"> & {qualityCounts: Record<string, number>, matchRate: number}} props */
function TaskPlanCountsSummary({ plan, counts, compact, qualityCounts, matchRate }) {
  const excluded = counts.notAnalyzed;
  if (compact) {
    return (
      <p className="task-count-line">
        {plan.record_count.toLocaleString()} 条用户反馈 ·{" "}
        {plan.valid_comment_count.toLocaleString()} 条有文本 · 合并为{" "}
        {counts.unique.toLocaleString()} 组评论
      </p>
    );
  }
  return (
    <div className="plan-overview">
      <div>
        <span>用户反馈</span>
        <strong>{plan.record_count.toLocaleString()}</strong>
      </div>
      <div>
        <span>有文本记录</span>
        <strong>{plan.valid_comment_count.toLocaleString()}</strong>
      </div>
      <div>
        <span>去重评论</span>
        <strong>{counts.unique.toLocaleString()}</strong>
      </div>
      <div>
        <span>可执行评论</span>
        <strong>{counts.executable.toLocaleString()}</strong>
      </div>
      <div className={excluded > 0 ? "is-warning" : undefined}>
        <span>不分析评论</span>
        <strong>{excluded.toLocaleString()}</strong>
      </div>
      <div
        className={
          Number(qualityCounts.unmatched_records || 0) > 0 ? "is-warning" : undefined
        }
      >
        <span>商品记录匹配率</span>
        <strong>{matchRate.toFixed(2)}%</strong>
      </div>
    </div>
  );
}

/** @param {Pick<PlanOverviewProps, "plan" | "counts">} props */
function TaskPlanReconciliation({ plan, counts }) {
  const excluded = counts.notAnalyzed;
  return (
    <div
      className={classNames(
        "plan-count-reconciliation",
        !counts.reconciled && "warning",
      )}
      role="status"
    >
      {counts.reconciled ? (
        <CheckCircle size={19} weight="fill" />
      ) : (
        <WarningCircle size={19} />
      )}
      <div>
        <b>
          {counts.reconciled
            ? `去重评论已对账：${counts.unique.toLocaleString()} = ${counts.executable.toLocaleString()} + ${excluded.toLocaleString()}`
            : "评论数量口径未对齐"}
        </b>
        <p>
          {plan.valid_comment_count.toLocaleString()} 条有文本记录合并为{" "}
          {counts.unique.toLocaleString()} 组评论；可执行覆盖率 {counts.coverageLabel}。
        </p>
      </div>
    </div>
  );
}
