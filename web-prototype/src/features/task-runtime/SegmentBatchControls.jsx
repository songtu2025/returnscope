import { useState } from "react";
import { Modal } from "../../components/SharedUi";
import { segmentActionAvailable, SEGMENT_STATUS_LABELS } from "./segmentBoardRowPolicy";
import "./segmentBatchControls.css";

/** @type {Record<import("./taskSegmentBatchActions").BatchSegmentAction, string>} */
const LABELS = { pause: "暂停", resume: "继续／重新排队", delete: "移除" };
/**
 * @param {{selection: ReturnType<typeof import("./useSegmentSelection").useSegmentSelection>,
 * disabled: boolean, onApply: import("./taskSegmentBatchActions").ApplySegmentBatch,
 * onRefresh: () => Promise<boolean>, readRequired?: boolean}} props
 */
export function SegmentBatchControls({
  selection,
  disabled,
  onApply,
  onRefresh,
  readRequired = false,
}) {
  const [planned, setPlanned] = useState(
    /** @type {{action: import("./taskSegmentBatchActions").BatchSegmentAction, items: typeof selection.selected} | null} */ (
      null
    ),
  );
  const [reading, setReading] = useState(false);
  const [readError, setReadError] = useState("");
  const { selected, result, busy } = selection;
  const action = planned?.action;
  const plannedItems = planned?.items ?? [];
  const needsRead = readRequired || result?.refreshRequired;
  const locked = disabled || busy || reading;
  const targets = action
    ? plannedItems.filter((item) => segmentActionAvailable(item, action))
    : [];
  const confirm = async () => {
    if (!action || locked || needsRead) return;
    await selection.apply(async () => {
      const result = await onApply(
        targets.map((item) => item.segment_key),
        action,
      );
      const skipped = plannedItems
        .filter((item) => !targets.includes(item))
        .map((item) => item.segment_key);
      return result ? { ...result, skipped: [...skipped, ...result.skipped] } : false;
    });
    setPlanned(null);
  };
  const refresh = async () => {
    if (locked) return;
    setReading(true);
    setReadError("");
    try {
      if (await onRefresh())
        selection.setResult((current) =>
          current ? { ...current, refreshRequired: false } : null,
        );
      else setReadError("读取失败，请重试读取；尚未重新提交操作。");
    } catch {
      setReadError("读取失败，请重试读取；尚未重新提交操作。");
    } finally {
      setReading(false);
    }
  };
  if (!selected.length && !result && !needsRead) return null;
  return (
    <section
      className="segment-batch-controls"
      aria-label="批量 Listing 操作"
      aria-busy={busy}
    >
      <div className="segment-batch-toolbar">
        <b>已选择 {selected.length} 个 Listing</b>
        {Object.entries(LABELS).map(([value, label]) => {
          const kind =
            /** @type {import("./taskSegmentBatchActions").BatchSegmentAction} */ (
              value
            );
          const count = selected.filter((item) =>
            segmentActionAvailable(item, kind),
          ).length;
          return (
            <button
              key={kind}
              className={`${kind === "delete" ? "danger-button" : "secondary-button"} compact-button`}
              disabled={locked || !count || needsRead}
              onClick={() => setPlanned({ action: kind, items: selected })}
            >
              {label} {count} 项
            </button>
          );
        })}
        <button
          className="text-button"
          disabled={locked || !selected.length}
          onClick={selection.clear}
        >
          取消选择
        </button>
        {busy && <span role="status">正在逐项提交…</span>}
      </div>
      {selected.length > 0 && (
        <details>
          <summary>核对已选 Listing（跨页保留）</summary>
          <ul>
            {selected.map((item) => (
              <li key={item.segment_key}>
                {item.scope?.listing || item.segment_key} · {item.scope?.store} ·{" "}
                {SEGMENT_STATUS_LABELS[item.display_status || item.status]}
              </li>
            ))}
          </ul>
        </details>
      )}
      {result && (
        <div role={result.failed ? "alert" : "status"}>
          已提交 {result.succeeded.length} 项 · 失败{" "}
          {result.failed && !result.failed.uncertain ? 1 : 0} 项 · 待核对{" "}
          {result.failed?.uncertain ? 1 : 0} 项 · 未执行 {result.pending.length} 项 ·
          跳过 {result.skipped.length} 项
          {result.failed && (
            <p>
              {selected.find((item) => item.segment_key === result.failed?.key)?.scope
                ?.listing || "Listing"}
              ：{result.failed.message}。已停止后续提交，请核对最新状态后重试剩余项。
            </p>
          )}
        </div>
      )}
      {needsRead && (
        <>
          <p>最新任务状态尚未读取成功，继续操作前请先刷新核对。</p>
          <button
            className="secondary-button compact-button"
            disabled={locked}
            onClick={refresh}
          >
            {reading ? "读取中…" : "重新读取任务状态"}
          </button>
        </>
      )}
      {readError && <p role="alert">{readError}</p>}
      {action && (
        <Modal
          title={`批量${LABELS[action]} Listing`}
          onClose={() => !locked && setPlanned(null)}
        >
          <p>
            已选 {plannedItems.length} 项，本次可{LABELS[action]} {targets.length}{" "}
            项，将跳过 {plannedItems.length - targets.length} 项。
          </p>
          <ul>
            {plannedItems.map((item) => (
              <li key={item.segment_key}>
                {item.scope?.listing || item.segment_key} ·{" "}
                {segmentActionAvailable(item, action)
                  ? "本次执行"
                  : "跳过：当前状态不支持本次操作"}
              </li>
            ))}
          </ul>
          <p>
            {action === "delete"
              ? "移入回收站，不再参与任务执行和统计；运行项先保存并停止，已有分类结果和看板保留。"
              : action === "pause"
                ? "运行中的 Listing 提交暂停请求，停止后显示已暂停；其他符合条件的项立即暂停。"
                : "重新进入现有执行队列，遵守原并行限制。"}
          </p>
          <div className="modal-actions">
            <button
              className="secondary-button"
              disabled={locked}
              onClick={() => setPlanned(null)}
            >
              返回
            </button>
            <button
              className={action === "delete" ? "danger-button" : "primary-button"}
              disabled={locked || !targets.length}
              onClick={confirm}
            >
              {busy ? "正在提交…" : `确认${LABELS[action]} ${targets.length} 项`}
            </button>
          </div>
        </Modal>
      )}
    </section>
  );
}
