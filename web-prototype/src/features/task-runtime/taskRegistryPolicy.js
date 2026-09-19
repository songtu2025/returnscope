import { STATUS_LABELS } from "../../constants";
import { resultState } from "../classification-results/resultActionPolicy";
import {
  isLegacyResult,
  isPublishedResult,
  resultPublishStatus,
} from "./taskSegmentPolicy";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskSegment} TaskSegment */

const ACTIVE_TASK_STATUSES = ["queued", "running", "paused"];
export const FINAL_TASK_STATUSES = [
  "completed",
  "failed",
  "cancelled",
  "blocked",
  "partial",
];

/** @param {AnalysisTask | null | undefined} task */
function isActiveTask(task) {
  return Boolean(task && ACTIVE_TASK_STATUSES.includes(task.status));
}

/** @param {AnalysisTask} task */
export function taskFilterGroup(task) {
  if (task?.archived_at) return "archived";
  if (isActiveTask(task)) return "active";
  return "finished";
}

/** @param {TaskSegment} segment */
export function segmentNeedsAttention(segment) {
  return (
    ["failed", "blocked", "completed_with_errors"].includes(segment.status) ||
    resultPublishStatus(segment) === "failed" ||
    (isPublishedResult(segment) &&
      ["needs_review", "unusable"].includes(resultState(segment))) ||
    (segment.status === "paused" && Boolean(segment.error))
  );
}

/** @param {AnalysisTask} task */
export function taskSummary(task) {
  const segments = task.segments ?? [];
  const executable = segments.filter((segment) => segment.agent_key !== "unknown");
  const published = executable.filter(isPublishedResult);
  const legacy = executable.filter(isLegacyResult);
  const generated = published.length + legacy.length;
  const total = task.segments ? executable.length : (task.listing_count ?? 0);
  const ready = published.filter((segment) =>
    ["ready", "review-derived"].includes(resultState(segment)),
  ).length;
  const reviews = published.filter(
    (segment) => resultState(segment) === "needs_review",
  ).length;
  const unusable = published.filter(
    (segment) => resultState(segment) === "unusable",
  ).length;
  const unknown = generated - ready - reviews - unusable;
  const issues = executable.filter(segmentNeedsAttention).length;
  const excluded = segments.some((segment) => segment.agent_key === "unknown");
  const needsAttention =
    issues > 0 || excluded || ["failed", "blocked", "partial"].includes(task.status);
  const resultDescription = [
    ready > 0 && `${ready} 个可用`,
    reviews > 0 && `${reviews} 个需复核`,
    unusable > 0 && `${unusable} 个不可用`,
    unknown > 0 && `${unknown} 个质量未确认`,
  ]
    .filter(Boolean)
    .join(" · ");
  const issueDescription =
    issues > 0
      ? `${issues} 个 Listing 需处理`
      : needsAttention
        ? "查看任务原因并处理"
        : "";
  const partialQueue =
    task.status === "queued" &&
    Boolean(
      task.partial_queue ??
      (task.snapshot?.execution_plan?.unresolved_policy === "run_ready" &&
        Number(task.snapshot?.execution_plan?.summary?.blocked_count || 0) > 0),
    );
  return {
    total,
    generated,
    ready,
    reviews,
    unusable,
    unknown,
    issues,
    needsAttention,
    remaining: Math.max(total - generated, 0),
    resultDescription,
    issueDescription,
    statusLabel: partialQueue
      ? "部分排队"
      : (STATUS_LABELS[task.status] ?? task.status),
  };
}
