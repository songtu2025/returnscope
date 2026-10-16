/** @typedef {import("./taskPlanContracts").TaskExecutionPlan} TaskExecutionPlan */

/** @param {TaskExecutionPlan | null | undefined} plan @param {string[]} [selectedKeys] */
export function taskPlanCounts(plan, selectedKeys) {
  const unique = Number(plan?.unique_comment_count || 0);
  const originalExecutable = Number(plan?.executable_count || 0);
  const executable =
    selectedKeys && plan
      ? plan.segments
          .filter(
            (item) =>
              selectedKeys.includes(item.segment_key) && item.status !== "blocked",
          )
          .reduce((total, item) => total + item.unique_comments, 0)
      : originalExecutable;
  const originalExcluded = Number(
    plan?.excluded_count ??
      Math.max(
        Number(plan?.blocked_count || 0),
        Number(plan?.missing_category_count || 0),
        Number(plan?.unknown_category_count || 0),
      ),
  );
  const notAnalyzed = originalExcluded + originalExecutable - executable;
  const coverage = unique > 0 ? (executable / unique) * 100 : 0;
  return {
    unique,
    executable,
    notAnalyzed,
    reconciled: unique === originalExecutable + originalExcluded,
    coverageLabel: `${coverage < 10 ? coverage.toFixed(2) : coverage.toFixed(1)}%`,
  };
}
