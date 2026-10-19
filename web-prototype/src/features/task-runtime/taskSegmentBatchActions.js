import { taskMonitorApi, errorMessage, errorStatus } from "./taskMonitorRequests";
import { segmentActionAvailable } from "./segmentBoardRowPolicy";
import { refreshServerState } from "../../shared/serverState";

/** @typedef {"pause" | "resume" | "delete"} BatchSegmentAction */
/** @typedef {BatchSegmentAction | "restore" | "purge"} SerialSegmentAction */
/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {{id: string, taskId: string, key: string}} SegmentActionTarget */
/** @typedef {{succeeded: string[], skipped: string[], pending: string[], failed: {key: string, message: string, uncertain: boolean} | null, refreshRequired: boolean}} SegmentBatchResult */
/** @typedef {(keys: string[], action: BatchSegmentAction) => Promise<SegmentBatchResult | false>} ApplySegmentBatch */

/**
 * @param {import("./taskExecutionActions").TaskActionContext} context
 * @param {string[]} keys
 * @param {BatchSegmentAction} action
 * @returns {Promise<SegmentBatchResult>}
 */
export async function applySegmentBatch(context, keys, action) {
  const { setSelected, loadSelected, loadTasks, mutateCache, notify } = context;
  const result = await runSegmentBatch(
    keys.map((key) => ({ id: key, taskId: context.selected.id, key })),
    action,
    { initialTask: context.selected, onTaskUpdated: setSelected },
  );
  if (result.failed) {
    try {
      const latest = await loadSelected();
      result.refreshRequired = !latest;
    } catch {
      // 写入结果不明时保持阻断，用户只可重读，不能直接重发批量请求。
    }
  }
  if (result.succeeded.length) {
    const reads = await Promise.allSettled([
      loadTasks(true),
      refreshServerState(mutateCache, ["workbench", "data-assets", "task-recycle"]),
    ]);
    if (reads.some((read) => read.status === "rejected" || read.value === false)) {
      notify("Listing 操作结果已保留，关联列表刷新失败，可重试读取", "error");
    }
  }
  return result;
}

/** @param {import("./taskRuntimeContracts").TaskSegment} segment @param {SerialSegmentAction} action */
function available(segment, action) {
  if (action === "restore" || action === "purge") {
    return Boolean(
      segment.deleted_at &&
      !segment.removal_requested_at &&
      (action === "restore" || segment.status !== "running"),
    );
  }
  return segmentActionAvailable(segment, action);
}

/** @param {SegmentActionTarget[]} values @param {SerialSegmentAction} action @param {{initialTask?: AnalysisTask, onTaskUpdated?: (task: AnalysisTask) => void}} [options] @returns {Promise<SegmentBatchResult>} */
export async function runSegmentBatch(
  values,
  action,
  { initialTask, onTaskUpdated } = {},
) {
  const targets = [...new Map(values.map((target) => [target.id, target])).values()];
  const tasks = new Map(initialTask ? [[initialTask.id, initialTask]] : []);
  /** @type {SegmentBatchResult} */
  const result = {
    succeeded: [],
    skipped: [],
    pending: [],
    failed: null,
    refreshRequired: false,
  };
  for (const [index, target] of targets.entries()) {
    let submitted = false;
    try {
      const current =
        tasks.get(target.taskId) ?? (await taskMonitorApi.task(target.taskId));
      tasks.set(target.taskId, current);
      const segment = current.segments?.find((item) => item.segment_key === target.key);
      if (!segment || !available(segment, action)) {
        result.skipped.push(target.id);
        continue;
      }
      // 每次使用服务端刚返回的任务修订号，不能并发提交同一旧修订。
      submitted = true;
      const updated = await taskMonitorApi.controlTaskSegment(
        current.id,
        target.key,
        action,
        {
          expected_revision: current.revision,
          ...(action === "restore" || action === "purge" ? {} : { note: "" }),
        },
      );
      tasks.set(current.id, updated);
      result.succeeded.push(target.id);
      onTaskUpdated?.(updated);
    } catch (failure) {
      const status = Number(errorStatus(failure));
      result.failed = {
        key: target.id,
        message: errorMessage(failure),
        uncertain: submitted && (!status || status >= 500),
      };
      result.pending = targets.slice(index + 1).map((item) => item.id);
      result.refreshRequired = true;
      break;
    }
  }
  return result;
}
