import { CheckCircle, PlayCircle, WarningCircle } from "@phosphor-icons/react";
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
  form,
  selectedReturns,
  modelPolicy,
  system,
  requiresScopeConfirmation,
  scopeConfirmed,
  onScopeConfirmationChange,
  submitting,
  submitLabel,
  onSubmit,
  onBack,
}) {
  return (
    <div className="task-plan-workspace">
      <header className="task-plan-header">
        <div>
          <span>确定性任务预检</span>
          <h2>从商品匹配到品类执行片段</h2>
          <p>
            产品信息缺少品类时需先补齐；仅品类完整但无分类逻辑或范围缺失时可选择阻断策略。
          </p>
        </div>
        <button className="secondary-button" onClick={onBack}>
          修改任务配置
        </button>
      </header>

      <div className="task-plan-layout">
        <section className="task-plan-main">
          {preflight.status === "loading" && <PreflightProgress />}
          {preflight.status === "error" && (
            <div className="plan-state error" role="alert">
              <WarningCircle size={20} />
              <div>
                <b>执行计划预检失败</b>
                <p>{preflight.error}</p>
              </div>
              <button className="secondary-button" onClick={onRetryPreflight}>
                重新预检
              </button>
            </div>
          )}
          {preflight.data && (
            <>
              <PreflightProgress complete />
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
                            ? "部分可执行"
                            : "准备完成"}
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
                              ? `${planCounts.executable.toLocaleString()} / ${planCounts.unique.toLocaleString()} 组评论将进入语义分析，覆盖率 ${planCounts.coverageLabel}。`
                              : "所有片段均可执行，请确认计划后启动。"}
                    {" · "}计划哈希 {preflight.data.plan_hash.slice(0, 12)}…
                  </p>
                </div>
              </div>
              <ExecutionPlanSummary
                plan={preflight.data}
                quality={dataQuality}
                policy={unresolvedPolicy}
                onPolicyChange={onPolicyChange}
                onResolveCategories={onResolveCategories}
                segmentOrder={segmentOrder}
                onSegmentOrderChange={onSegmentOrderChange}
              />
            </>
          )}
        </section>

        <aside className="task-plan-sidebar">
          <div>
            <span>本次运行快照</span>
            <b>
              {form.title || `${selectedReturns?.dataset_name || "退货明细"} 语义分析`}
            </b>
            <p>
              自动识别 {preflight.data?.detected_scopes?.length ?? 0} 个数据范围 ·
              创建后配置不可变
            </p>
          </div>
          <dl>
            <div>
              <dt>退货明细</dt>
              <dd>
                {selectedReturns?.dataset_name} · v{selectedReturns?.version}
              </dd>
            </div>
            <div>
              <dt>模型策略</dt>
              <dd>
                {modelPolicy.cheap_model || "未启用"} / {modelPolicy.primary_model} /{" "}
                {modelPolicy.secondary_model || "未启用"}
              </dd>
            </div>
            <div>
              <dt>初筛抽检</dt>
              <dd>{modelPolicy.cheap_audit_percent ?? 5}%</dd>
            </div>
            <div>
              <dt>并行名额</dt>
              <dd>{system?.my_running_tasks ?? 0}/3 已使用</dd>
            </div>
          </dl>
          {requiresScopeConfirmation && (
            <label className="task-scope-confirmation">
              <input
                type="checkbox"
                checked={scopeConfirmed}
                onChange={(event) => onScopeConfirmationChange(event.target.checked)}
              />
              <span>
                我确认本次仅分析 {planCounts.executable.toLocaleString()} 组评论，
                {planCounts.notAnalyzed.toLocaleString()} 组不进入模型。
              </span>
            </label>
          )}
          <button
            className="primary-button task-plan-button"
            disabled={
              submitting ||
              preflight.status !== "ready" ||
              !unresolvedPolicy ||
              categoryCompletionRequired ||
              countMismatch ||
              noExecutable ||
              (requiresScopeConfirmation && !scopeConfirmed)
            }
            onClick={onSubmit}
          >
            {submitting
              ? "正在创建…"
              : preflight.status === "loading"
                ? "正在生成计划…"
                : submitLabel}
            <PlayCircle size={18} />
          </button>
          <p className="task-plan-next-step" role="status">
            启动后会自动跳转到“分析任务”，可持续查看进度、日志和异常处理入口。
          </p>
        </aside>
      </div>
    </div>
  );
}
