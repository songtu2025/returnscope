import { resultActionPolicy } from "./resultActionPolicy";

/** @typedef {import("./classificationResultDetailContracts").ResultDetailViewProps} ResultDetailViewProps */

/** @param {Pick<ResultDetailViewProps,"result"|"summary"|"records"|"route"|"recordsLoading"|"drilldowns">} props */
export function resultDetailPresentation({
  result,
  summary,
  records,
  route,
  recordsLoading,
  drilldowns,
}) {
  const isUserFeedback = result.analysis_context === "user_feedback";
  const totalPages = Math.max(Math.ceil((records?.total ?? 0) / route.pageSize), 1);
  const readyRecords = resultQualityCount(summary, ["ready"]);
  const reviewRecords = resultQualityCount(summary, [
    "review_required",
    "needs_review",
  ]);
  const excludedRecords = resultQualityCount(summary, ["excluded"]);
  const unusableRecords = resultQualityCount(summary, ["unusable"]);
  const modelErrorRecords = resultModelErrorCount(summary);
  const accountedRecords = accountedRecordCount(
    readyRecords,
    reviewRecords,
    excludedRecords,
    unusableRecords,
  );
  const totalRecords = Number(result.record_count || 0);
  const policy = resultActionPolicy(result);
  const allNeedReviewWithoutProblems = needsReviewWithoutProblems(
    recordsLoading,
    drilldowns,
    reviewRecords,
    result,
  );
  return {
    isUserFeedback,
    totalPages,
    readyRecords,
    reviewRecords,
    excludedRecords,
    unusableRecords,
    modelErrorRecords,
    accountedRecords,
    totalRecords,
    policy,
    allNeedReviewWithoutProblems,
  };
}
/** @param {ResultDetailViewProps["summary"]} summary @param {string[]} statuses */
function resultQualityCount(summary, statuses) {
  return summary?.quality?.find((item) => statuses.includes(item.quality_status))
    ?.record_count;
}
/** @param {ResultDetailViewProps["summary"]} summary */
function resultModelErrorCount(summary) {
  return summary?.processing_statuses?.find(
    (item) => item.processing_status === "MODEL_ERROR",
  )?.record_count;
}
/** @param {boolean} recordsLoading @param {ResultDetailViewProps["drilldowns"]} drilldowns @param {number|undefined} reviewRecords @param {ResultDetailViewProps["result"]} result */
function needsReviewWithoutProblems(recordsLoading, drilldowns, reviewRecords, result) {
  return (
    Number(reviewRecords) === Number(result.record_count) &&
    !recordsLoading &&
    drilldowns.problem.length === 0 &&
    Number(reviewRecords || result.record_count || 0) > 0
  );
}

/** @param {number | undefined} readyRecords @param {number | undefined} reviewRecords @param {number | undefined} excludedRecords @param {number | undefined} unusableRecords */
function accountedRecordCount(
  readyRecords,
  reviewRecords,
  excludedRecords,
  unusableRecords,
) {
  return (
    Number(readyRecords || 0) +
    Number(reviewRecords || 0) +
    Number(excludedRecords || 0) +
    Number(unusableRecords || 0)
  );
}
