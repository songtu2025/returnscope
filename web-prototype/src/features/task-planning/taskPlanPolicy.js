export function taskPlanCounts(plan) {
  const unique = Number(plan?.unique_comment_count || 0);
  const executable = Number(plan?.executable_count || 0);
  const notAnalyzed = Number(
    plan?.excluded_count ??
      Math.max(
        Number(plan?.blocked_count || 0),
        Number(plan?.missing_category_count || 0),
        Number(plan?.unknown_category_count || 0),
      ),
  );
  const coverage = unique > 0 ? (executable / unique) * 100 : 0;
  return {
    unique,
    executable,
    notAnalyzed,
    reconciled: unique === executable + notAnalyzed,
    coverageLabel: `${coverage < 10 ? coverage.toFixed(2) : coverage.toFixed(1)}%`,
  };
}
