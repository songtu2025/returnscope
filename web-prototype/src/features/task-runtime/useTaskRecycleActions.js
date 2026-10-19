import { useRef, useState } from "react";
import { taskMonitorApi } from "./taskMonitorRequests";
import { runSegmentBatch } from "./taskSegmentBatchActions";

/** @typedef {import("./taskRecycleContracts").RecycledListing} RecycledListing */
/** @typedef {import("./taskRecycleContracts").RecycleResult} RecycleResult */
/** @param {{notify: (message: string, type?: "success" | "error") => void, removeItems: (ids: string[]) => Promise<void>, refreshAfterAction: () => Promise<void>, clearSelection: () => void}} options */
export function useTaskRecycleActions({
  notify,
  removeItems,
  refreshAfterAction,
  clearSelection,
}) {
  const lock = useRef(false);
  const [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState(
    /** @type {import("./taskRecycleContracts").RecycleSelection | null} */ (null),
  );
  const [result, setResult] = useState(/** @type {RecycleResult | null} */ (null));
  const [restored, setRestored] = useState(
    /** @type {RecycledListing | null} */ (null),
  );
  /** @param {RecycleResult} outcome */
  const verify = async (outcome) => {
    if (!outcome.failed?.uncertain) return outcome;
    const item = outcome.items.find((row) => row.id === outcome.failed?.key);
    if (!item) return outcome;
    try {
      const task = await taskMonitorApi.task(item.task_id);
      const segment = task.segments?.find(
        (row) => row.segment_key === item.segment_key,
      );
      const completed =
        outcome.action === "restore"
          ? Boolean(segment && !segment.deleted_at)
          : !segment;
      return completed
        ? { ...outcome, succeeded: [...outcome.succeeded, item.id], failed: null }
        : { ...outcome, failed: { ...outcome.failed, uncertain: false } };
    } catch {
      return outcome;
    }
  };
  /** @param {RecycleResult} outcome */
  const publish = async (outcome) => {
    setResult(outcome);
    if (outcome.succeeded.length) {
      await removeItems(outcome.succeeded);
      if (outcome.action === "restore")
        setRestored(
          outcome.items.find((item) => outcome.succeeded.includes(item.id)) ?? null,
        );
      notify(
        outcome.items.length === 1
          ? outcome.action === "restore"
            ? "Listing 已恢复，不会自动执行"
            : "Listing 已永久删除，已有产出保留"
          : `已${outcome.action === "restore" ? "恢复" : "永久删除"} ${outcome.succeeded.length} 条`,
      );
    }
    if (outcome.failed) notify(outcome.failed.message, "error");
    clearSelection();
    await refreshAfterAction();
  };
  /** @param {RecycledListing[]} items @param {import("./taskRecycleContracts").RecycleAction} action */
  const execute = async (items, action) => {
    if (lock.current || result?.failed?.uncertain) return;
    lock.current = true;
    setBusy(true);
    try {
      const outcome = await runSegmentBatch(
        items.map((item) => ({
          id: item.id,
          taskId: item.task_id,
          key: item.segment_key,
        })),
        action,
      );
      setConfirmation(null);
      await publish(await verify({ ...outcome, items, action }));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  const verifyResult = async () => {
    if (lock.current || !result?.failed?.uncertain) return;
    lock.current = true;
    setBusy(true);
    try {
      const checked = await verify(result);
      // 仅移除这次核实新增的成功项，不重复报告已经确认的成功。
      setResult(checked);
      await removeItems(checked.succeeded);
      await refreshAfterAction();
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  return {
    busy,
    blocked: busy || Boolean(result?.failed?.uncertain),
    confirmation,
    setConfirmation,
    result,
    restored,
    execute,
    verifyResult,
  };
}
