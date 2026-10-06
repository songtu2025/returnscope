import {
  ArrowRight,
  CheckCircle,
  Database,
  Pulse,
  WarningCircle,
} from "@phosphor-icons/react";
import { classNames } from "../../lib/presentation";
import { taskPlanCounts } from "./taskPlanPolicy";
import { ExecutionPlanSegments } from "./ExecutionPlanSegments";

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
  const blocked = plan.blocked_count > 0;
  const counts = taskPlanCounts(plan);
  const excluded = counts.notAnalyzed;
  const categoryCompletionRequired = Boolean(plan.category_completion_required);
  const missingCategoryComments = categoryCompletionRequired
    ? (plan.missing_category_comment_count ?? plan.missing_category_count ?? 0)
    : 0;
  const missingCategoryProducts = plan.missing_category_product_count ?? 0;
  const qualityCounts = quality?.counts ?? {};
  const qualityTotal = Number(qualityCounts.total_records || 0);
  const qualityMatched = Number(qualityCounts.matched_records || 0);
  const matchRate = qualityTotal > 0 ? (qualityMatched / qualityTotal) * 100 : 0;
  const exclusionReasons = [
    Number(plan.unmatched_product_count || 0) > 0 &&
      `产品信息未匹配 ${Number(plan.unmatched_product_count).toLocaleString()} 组`,
    Number(plan.missing_category_count || 0) > 0 &&
      `缺失品类 ${Number(plan.missing_category_count).toLocaleString()} 组`,
    Number(plan.unknown_category_count || 0) > 0 &&
      `未配置分类逻辑 ${Number(plan.unknown_category_count).toLocaleString()} 组`,
    Number(plan.unresolved_scope_count || 0) > 0 &&
      `范围未识别 ${Number(plan.unresolved_scope_count).toLocaleString()} 组`,
  ].filter(Boolean);
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
  const detectedStores = new Set(
    (plan.detected_scopes ?? []).map((scope) => scope.store).filter(Boolean),
  );
  const detectedListings = new Set(
    (plan.detected_scopes ?? []).map((scope) => scope.listing).filter(Boolean),
  );
  const segmentsView = (
    <ExecutionPlanSegments
      orderedSegments={orderedSegments}
      onSegmentOrderChange={onSegmentOrderChange}
    />
  );
  return (
    <section className="execution-plan" aria-label="真实品类执行计划">
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
      {compact ? (
        <p className="task-count-line">
          {plan.record_count.toLocaleString()} 条用户反馈 ·{" "}
          {plan.valid_comment_count.toLocaleString()} 条有文本 · 合并为{" "}
          {counts.unique.toLocaleString()} 组评论
        </p>
      ) : (
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
              Number(qualityCounts.unmatched_records || 0) > 0
                ? "is-warning"
                : undefined
            }
          >
            <span>商品记录匹配率</span>
            <strong>{matchRate.toFixed(2)}%</strong>
          </div>
        </div>
      )}
      {(!compact || !counts.reconciled) && (
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
              {counts.unique.toLocaleString()} 组评论；可执行覆盖率{" "}
              {counts.coverageLabel}。
            </p>
          </div>
        </div>
      )}
      {!compact && segmentsView}
      {categoryCompletionRequired && (
        <div className="unresolved-plan category-completion-plan" role="alert">
          <WarningCircle size={20} />
          <div>
            <b>
              {missingCategoryProducts.toLocaleString()} 个商品缺少品类A或品类B，影响{" "}
              {missingCategoryComments.toLocaleString()} 条评论
            </b>
            <p>
              品类是智能体路由的必填信息。补齐后会生成新的产品信息版本，并自动重新预检；在此之前不能创建任务。
            </p>
            {onResolveCategories && (
              <button
                type="button"
                className="secondary-button"
                onClick={onResolveCategories}
              >
                补齐商品品类
                <ArrowRight size={16} />
              </button>
            )}
          </div>
        </div>
      )}
      {excluded > 0 && (
        <div className="excluded-plan" role="status">
          <WarningCircle size={20} />
          <div>
            <b>{excluded.toLocaleString()} 组评论不进入语义分析</b>
            <p>
              {exclusionReasons.length > 0
                ? `原因：${exclusionReasons.join("；")}。`
                : "系统已将不可执行评论排除。"}
              系统会保留排除数量，不调用模型。
            </p>
            {!categoryCompletionRequired &&
              onResolveCategories &&
              exclusionReasons.length > 0 && (
                <button
                  type="button"
                  className="secondary-button"
                  onClick={onResolveCategories}
                >
                  处理排除原因
                  <ArrowRight size={16} />
                </button>
              )}
          </div>
        </div>
      )}
      {blocked && (
        <div className="unresolved-plan" role="alert">
          <WarningCircle size={20} />
          <div>
            <b>存在 {plan.blocked_count.toLocaleString()} 条无法映射到智能体的评论</b>
            <p>
              未配置分类逻辑 {(plan.unknown_category_count ?? 0).toLocaleString()}{" "}
              条；范围未识别 {(plan.unresolved_scope_count ?? 0).toLocaleString()} 条。
            </p>
            <div className="unresolved-categories">
              {plan.unknown_categories.map((variant) => (
                <span key={`${variant.category_a}-${variant.category_b}`}>
                  {variant.category_a} / {variant.category_b} ·{" "}
                  {variant.record_count.toLocaleString()} 条
                </span>
              ))}
            </div>
            {onResolveCategories && (
              <button
                type="button"
                className="secondary-button"
                onClick={onResolveCategories}
              >
                {plan.unresolved_product_count
                  ? `处理 ${plan.unresolved_product_count.toLocaleString()} 个商品匹配异常`
                  : "前往补充商品信息"}
                <ArrowRight size={16} />
              </button>
            )}
          </div>
        </div>
      )}
      {blocked && onPolicyChange && (
        <fieldset className="plan-policy">
          <legend>选择未解决品类处理方式</legend>
          <label>
            <input
              type="radio"
              name="unresolved-policy"
              value="block_all"
              checked={policy === "block_all"}
              onChange={(event) => onPolicyChange(event.target.value)}
            />
            <span>
              <b>全部阻断</b>
              等待品类配置完成后再运行所有片段
            </span>
          </label>
          <label>
            <input
              type="radio"
              name="unresolved-policy"
              value="run_ready"
              checked={policy === "run_ready"}
              onChange={(event) => onPolicyChange(event.target.value)}
            />
            <span>
              <b>先运行已就绪</b>
              只启动已匹配品类，未知品类保持阻断
            </span>
          </label>
        </fieldset>
      )}
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
