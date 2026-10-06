import { ArrowRight, WarningCircle } from "@phosphor-icons/react";

/** @typedef {import("./taskPlanContracts").TaskExecutionPlan} TaskExecutionPlan */
/** @typedef {import("./taskPlanContracts").TaskPlanCounts} TaskPlanCounts */
/** @typedef {{plan: TaskExecutionPlan, counts: TaskPlanCounts, policy?: string, onPolicyChange?: (policy: string) => void, onResolveCategories?: () => void}} PlanIssuesProps */

/** @param {PlanIssuesProps} props */
export function ExecutionPlanIssues({
  plan,
  counts,
  policy,
  onPolicyChange,
  onResolveCategories,
}) {
  const blocked = plan.blocked_count > 0;
  const excluded = counts.notAnalyzed;
  const categoryCompletionRequired = Boolean(plan.category_completion_required);
  const missingCategoryComments = categoryCompletionRequired
    ? (plan.missing_category_comment_count ?? plan.missing_category_count ?? 0)
    : 0;
  const missingCategoryProducts = plan.missing_category_product_count ?? 0;
  const exclusionReasons = taskPlanExclusionReasons(plan);
  return (
    <>
      {categoryCompletionRequired && (
        <TaskPlanCategoryIssue
          missingCategoryProducts={missingCategoryProducts}
          missingCategoryComments={missingCategoryComments}
          onResolveCategories={onResolveCategories}
        />
      )}
      {excluded > 0 && (
        <TaskPlanExclusions
          excluded={excluded}
          exclusionReasons={exclusionReasons}
          categoryCompletionRequired={categoryCompletionRequired}
          onResolveCategories={onResolveCategories}
        />
      )}
      {blocked && (
        <TaskPlanBlockedComments
          plan={plan}
          onResolveCategories={onResolveCategories}
        />
      )}
      {blocked && onPolicyChange && (
        <TaskPlanUnresolvedPolicy policy={policy} onPolicyChange={onPolicyChange} />
      )}
    </>
  );
}

/** @param {{missingCategoryProducts: number, missingCategoryComments: number, onResolveCategories?: () => void}} props */
function TaskPlanCategoryIssue({
  missingCategoryProducts,
  missingCategoryComments,
  onResolveCategories,
}) {
  return (
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
  );
}

/** @param {{excluded: number, exclusionReasons: (string | false)[], categoryCompletionRequired: boolean, onResolveCategories?: () => void}} props */
function TaskPlanExclusions({
  excluded,
  exclusionReasons,
  categoryCompletionRequired,
  onResolveCategories,
}) {
  return (
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
  );
}

/** @param {Pick<PlanIssuesProps, "plan" | "onResolveCategories">} props */
function TaskPlanBlockedComments({ plan, onResolveCategories }) {
  return (
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
  );
}

/** @param {{policy?: string, onPolicyChange: (policy: string) => void}} props */
function TaskPlanUnresolvedPolicy({ policy, onPolicyChange }) {
  return (
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
  );
}

/** @param {TaskExecutionPlan} plan */
function taskPlanExclusionReasons(plan) {
  return [
    Number(plan.unmatched_product_count || 0) > 0 &&
      `产品信息未匹配 ${Number(plan.unmatched_product_count).toLocaleString()} 组`,
    Number(plan.missing_category_count || 0) > 0 &&
      `缺失品类 ${Number(plan.missing_category_count).toLocaleString()} 组`,
    Number(plan.unknown_category_count || 0) > 0 &&
      `未配置分类逻辑 ${Number(plan.unknown_category_count).toLocaleString()} 组`,
    Number(plan.unresolved_scope_count || 0) > 0 &&
      `范围未识别 ${Number(plan.unresolved_scope_count).toLocaleString()} 组`,
  ].filter(Boolean);
}
