import { CheckCircle, WarningCircle } from "@phosphor-icons/react";
import { useEffect, useRef } from "react";
import {
  ExecutionPlanSummary,
  PreflightProgress,
} from "../task-planning/ExecutionPlanSummary";
import { classNames } from "../../lib/presentation";

/** @typedef {import("./taskCreateContracts").TaskPreflightState} TaskPreflightState */
/** @typedef {import("../task-planning/taskPlanContracts").TaskDataQuality} TaskDataQuality */
/** @typedef {import("../task-planning/taskPlanContracts").TaskPlanCounts} TaskPlanCounts */
/**
 * @param {{preflight: TaskPreflightState, onRetryPreflight: () => void | Promise<unknown>, categoryCompletionRequired: boolean, blocked: boolean, countMismatch: boolean, noExecutable: boolean, partialPlan: boolean, planCounts: TaskPlanCounts, dataQuality: TaskDataQuality | null, unresolvedPolicy: string, onPolicyChange: (policy: string) => void, onResolveCategories: () => void, segmentOrder: string[], onSegmentOrderChange: (order: string[]) => void, requiresScopeConfirmation: boolean, scopeConfirmed: boolean, onScopeConfirmationChange: (confirmed: boolean) => void}} props
 */

export function TaskPlanReviewStep({
  preflight,
  onRetryPreflight,
  categoryCompletionRequired,
  blocked,
  countMismatch,
  noExecutable,
  partialPlan,
  planCounts,
  dataQuality,
  unresolvedPolicy,
  onPolicyChange,
  onResolveCategories,
  segmentOrder,
  onSegmentOrderChange,
  requiresScopeConfirmation,
  scopeConfirmed,
  onScopeConfirmationChange,
}) {
  const workspaceRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const retryFocus = useRef(false);
  useEffect(() => {
    if (retryFocus.current && preflight.status !== "loading") {
      retryFocus.current = false;
      workspaceRef.current?.focus();
    }
  }, [preflight.status]);
  return (
    <div ref={workspaceRef} className="task-plan-workspace" tabIndex={-1}>
      <div className="task-plan-layout">
        <section className="task-plan-main">
          {preflight.status === "loading" && <PreflightProgress />}
          {preflight.status === "error" && (
            <div className="plan-state error" role="alert">
              <WarningCircle size={20} />
              <div>
                <b>暂时无法完成检查</b>
                <p>{preflight.error}</p>
              </div>
              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  retryFocus.current = true;
                  workspaceRef.current?.focus();
                  void onRetryPreflight();
                }}
              >
                重新检查
              </button>
            </div>
          )}
          {preflight.data && (
            <>
              <PlanStateNotice
                state={{
                  categoryCompletionRequired,
                  blocked,
                  countMismatch,
                  noExecutable,
                  partialPlan,
                }}
                planCounts={planCounts}
              />
              <ExecutionPlanSummary
                compact
                plan={preflight.data}
                quality={dataQuality}
                policy={unresolvedPolicy}
                onPolicyChange={onPolicyChange}
                onResolveCategories={onResolveCategories}
                segmentOrder={segmentOrder}
                onSegmentOrderChange={onSegmentOrderChange}
              />
              {requiresScopeConfirmation && (
                <label className="task-scope-confirmation">
                  <input
                    type="checkbox"
                    checked={scopeConfirmed}
                    onChange={(event) =>
                      onScopeConfirmationChange(event.target.checked)
                    }
                  />
                  <span>
                    我确认本次仅分析 {planCounts.executable.toLocaleString()} 组评论，
                    {planCounts.notAnalyzed.toLocaleString()} 组不进入模型。
                  </span>
                </label>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}

/** @typedef {{categoryCompletionRequired: boolean, blocked: boolean, countMismatch: boolean, noExecutable: boolean, partialPlan: boolean}} PlanNoticeState */

/** @param {{state: PlanNoticeState, planCounts: TaskPlanCounts}} props */
function PlanStateNotice({ state, planCounts }) {
  const notice = planReviewNotice(state, planCounts);
  return (
    <div
      className={classNames("plan-state", notice.warning ? "warning" : "success")}
      role="status"
    >
      {notice.warning ? (
        <WarningCircle size={20} />
      ) : (
        <CheckCircle size={20} weight="fill" />
      )}
      <div>
        <b>{notice.title}</b>
        <p>{notice.description}</p>
      </div>
    </div>
  );
}

/** @param {PlanNoticeState} state @param {TaskPlanCounts} counts */
function planReviewNotice(state, counts) {
  if (state.categoryCompletionRequired)
    return {
      warning: true,
      title: "需要处理",
      description: "先补齐产品信息中的品类A和品类B，重新预检后才能创建任务。",
    };
  if (state.blocked)
    return {
      warning: true,
      title: "需要处理",
      description: "补充商品信息，或选择如何处理已就绪片段。",
    };
  if (state.countMismatch)
    return {
      warning: true,
      title: "数量口径异常",
      description: "去重评论无法与可执行和不分析评论对账，请重新预检或联系管理员。",
    };
  if (state.noExecutable)
    return {
      warning: true,
      title: "不可执行",
      description: "当前没有可执行评论，请补充品类或调整数据范围。",
    };
  if (state.partialPlan)
    return {
      warning: true,
      title: `将分析 ${counts.executable.toLocaleString()} 组评论`,
      description: `另有 ${counts.notAnalyzed.toLocaleString()} 组评论不进入分析，请查看原因并确认。`,
    };
  return {
    warning: false,
    title: `已准备好 ${counts.executable.toLocaleString()} 组评论`,
    description: "数据检查完成，可以开始分析。",
  };
}
