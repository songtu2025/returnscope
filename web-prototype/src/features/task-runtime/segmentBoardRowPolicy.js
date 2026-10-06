import {
  resultState,
  resultStateLabel,
} from "../classification-results/resultActionPolicy";
import { isPublishedResult, resultPublishStatus } from "./taskSegmentPolicy";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskSegment} TaskSegment */
const RETRYABLE_SEGMENT_STATUSES = ["failed", "completed_with_errors", "not_started"];
export const SEGMENT_STATUS_LABELS = {
  ready: "可执行",
  queued: "等待",
  running: "运行中",
  pause_pending: "正在暂停",
  cancel_pending: "正在取消",
  paused: "已暂停",
  completed: "已完成",
  completed_with_errors: "完成但有异常",
  failed: "失败",
  blocked: "未纳入分析",
  cancelled: "已取消",
  not_started: "尚未运行",
  retry_pending: "等待重试",
};

/** @param {unknown} value */
function shortPublishError(value) {
  const message = String(value || "未返回具体原因")
    .replace(/\s+/g, " ")
    .trim();
  return message.length > 80 ? `${message.slice(0, 80)}…` : message;
}

/** @param {AnalysisTask} task @param {TaskSegment} segment */
export function canRetrySegment(task, segment) {
  if (["queued", "running"].includes(task.status)) return false;
  if (segment.agent_key === "unknown" || segment.status === "blocked") return false;
  if (isPublishedResult(segment)) return false;
  if (!RETRYABLE_SEGMENT_STATUSES.includes(segment.status)) return false;
  const blockedExists = task.segments?.some((item) => item.status === "blocked");
  const policy = task.snapshot?.execution_plan?.unresolved_policy ?? "block_all";
  return !(segment.status === "not_started" && policy === "block_all" && blockedExists);
}

/** @param {TaskSegment} segment */
export function segmentResultPresentation(segment) {
  const displayStatus = segment.display_status || segment.status;
  const publishStatus = resultPublishStatus(segment);
  const qualityResult = {
    result_state: segment.result_state,
    result_quality_status: segment.result_quality_status,
    source_review_batch_id: segment.source_review_batch_id,
    publish_status: publishStatus,
  };
  const qualityState = resultState(qualityResult);
  const qualityLabel = resultStateLabel(qualityResult);
  const stateLabel =
    publishStatus === "publishing"
      ? "正在生成结果"
      : publishStatus === "failed"
        ? "结果生成失败"
        : publishStatus === "published"
          ? qualityLabel
          : (SEGMENT_STATUS_LABELS[displayStatus] ?? displayStatus);
  const stateDescription =
    publishStatus === "publishing"
      ? "分类已完成，正在生成结果"
      : publishStatus === "failed"
        ? shortPublishError(segment.result_publish_error)
        : publishStatus === "published"
          ? "结果已生成"
          : segment.wait_reason;
  return { displayStatus, publishStatus, qualityState, stateLabel, stateDescription };
}
