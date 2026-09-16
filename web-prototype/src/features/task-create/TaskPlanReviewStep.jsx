import { CheckCircle, WarningCircle } from "@phosphor-icons/react";
import {
  ExecutionPlanSummary,
  PreflightProgress,
} from "../task-planning/ExecutionPlanSummary";
import { classNames } from "../../lib/presentation";

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
  return (
    <div className="task-plan-workspace">
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
                onClick={onRetryPreflight}
              >
                重新检查
              </button>
            </div>
          )}
          {preflight.data && (
            <>
              <div
                className={classNames(
                  "plan-state",
                  categoryCompletionRequired ||
                    blocked ||
                    countMismatch ||
                    noExecutable ||
                    partialPlan
                    ? "warning"
                    : "success",
                )}
                role="status"
              >
                {categoryCompletionRequired ||
                blocked ||
                countMismatch ||
                noExecutable ||
                partialPlan ? (
                  <WarningCircle size={20} />
                ) : (
                  <CheckCircle size={20} weight="fill" />
                )}
                <div>
                  <b>
                    {categoryCompletionRequired || blocked
                      ? "需要处理"
                      : countMismatch
                        ? "数量口径异常"
                        : noExecutable
                          ? "不可执行"
                          : partialPlan
                            ? `将分析 ${planCounts.executable.toLocaleString()} 组评论`
                            : `已准备好 ${planCounts.executable.toLocaleString()} 组评论`}
                  </b>
                  <p>
                    {categoryCompletionRequired
                      ? "先补齐产品信息中的品类A和品类B，重新预检后才能创建任务。"
                      : blocked
                        ? "补充商品信息，或选择如何处理已就绪片段。"
                        : countMismatch
                          ? "去重评论无法与可执行和不分析评论对账，请重新预检或联系管理员。"
                          : noExecutable
                            ? "当前没有可执行评论，请补充品类或调整数据范围。"
                            : partialPlan
                              ? `另有 ${planCounts.notAnalyzed.toLocaleString()} 组评论不进入分析，请查看原因并确认。`
                              : "数据检查完成，可以开始分析。"}
                  </p>
                </div>
              </div>
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
