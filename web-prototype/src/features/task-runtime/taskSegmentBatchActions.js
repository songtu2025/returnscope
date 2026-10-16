import { taskMonitorApi, errorMessage, errorStatus } from "./taskMonitorRequests";
import { segmentActionAvailable } from "./segmentBoardRowPolicy";
import { refreshServerState } from "../../shared/serverState";

/** @typedef {"pause" | "resume" | "delete"} BatchSegmentAction */
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
  let current = context.selected;
  const targets = [...new Set(keys)];
  /** @type {SegmentBatchResult} */
  const result = {
    succeeded: [],
    skipped: [],
    pending: [],
    failed: null,
    refreshRequired: false,
  };
  for (const [index, key] of targets.entries()) {
    const segment = current.segments?.find((item) => item.segment_key === key);
    if (!segment || !segmentActionAvailable(segment, action)) {
      result.skipped.push(key);
      continue;
    }
    try {
      // 每次使用服务端刚返回的任务修订号，不能并发提交同一旧修订。
      current = await taskMonitorApi.controlTaskSegment(current.id, key, action, {
        expected_revision: current.revision,
        note: "",
      });
    } catch (failure) {
      const status = Number(errorStatus(failure));
      result.failed = {
        key,
        message: errorMessage(failure),
        uncertain: !status || status >= 500,
      };
      result.pending = targets.slice(index + 1);
      result.refreshRequired = true;
      break;
    }
    result.succeeded.push(key);
    setSelected(current);
  }
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
