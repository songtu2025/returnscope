import { useEffect, useRef } from "react";

/** @param {{count: number, disabled: boolean, onRestore: () => void, onPurge: () => void, onClear: () => void}} props */
export function TaskRecycleSelection({ count, disabled, onRestore, onPurge, onClear }) {
  return (
    <div className="recycle-selection" role="group" aria-label="回收站批量操作">
      <span>当前页已选 {count} 条</span>
      <button
        className="primary-button"
        disabled={disabled || !count}
        onClick={onRestore}
      >
        批量恢复
      </button>
      <button
        className="secondary-button danger"
        disabled={disabled || !count}
        onClick={onPurge}
      >
        批量永久删除
      </button>
      <button className="text-button" disabled={disabled || !count} onClick={onClear}>
        取消选择
      </button>
    </div>
  );
}

/** @param {{result: import("./taskRecycleContracts").RecycleResult, busy: boolean, onVerify: () => void}} props */
export function TaskRecycleBatchResult({ result, busy, onVerify }) {
  const resultRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  useEffect(() => {
    resultRef.current?.focus();
  }, [result]);
  const state = (/** @type {string} */ id) => {
    if (result.succeeded.includes(id)) return "已确认完成";
    if (result.failed?.key === id)
      return result.failed.uncertain ? "结果待核实" : `失败：${result.failed.message}`;
    return result.skipped.includes(id) ? "状态已变化，未执行" : "未处理";
  };
  return (
    <div
      className="recycle-batch-result"
      role="region"
      aria-label="回收站操作结果"
      tabIndex={-1}
      ref={resultRef}
    >
      <p>
        已确认完成 {result.succeeded.length} 条 ·{" "}
        {result.failed?.uncertain ? "待核实" : "失败"} {result.failed ? 1 : 0} 条 ·
        未处理 {result.pending.length} 条 · 状态变化 {result.skipped.length} 条
      </p>
      {result.pending.length > 0 && (
        <p>操作已停止，剩余记录未提交。核对结果后可重新选择。</p>
      )}
      {result.failed?.uncertain && (
        <p>
          提交结果不明，已暂停新的写入；请先只读核实。
          <button className="secondary-button" disabled={busy} onClick={onVerify}>
            刷新核实结果
          </button>
        </p>
      )}
      <details>
        <summary>查看逐项结果</summary>
        <ul>
          {result.items.map((item) => (
            <li key={item.id}>
              {item.scope.listing} · {item.scope.store} · {item.task_title}（
              {item.task_id}）：{state(item.id)}
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
