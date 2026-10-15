import "./taskRegistrySelection.css";
import { Archive, ArrowCounterClockwise } from "@phosphor-icons/react";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @param {{selected: AnalysisTask[], visibleIds: string[], executableIds: string[], archived: boolean, saving: boolean, onApply: () => void, onRemove: (id: string) => void, onClear: () => void}} props */
export function TaskRegistrySelection({
  selected,
  visibleIds,
  executableIds,
  archived,
  saving,
  onApply,
  onRemove,
  onClear,
}) {
  return (
    <div className="task-registry-batch" role="region" aria-label="批量任务操作">
      <div className="task-selection-summary">
        <b>已选择 {selected.length} 个任务</b>
        <span>
          当前列表可操作 {executableIds.length} 个 · 当前不可操作{" "}
          {selected.filter((task) => visibleIds.includes(task.id)).length -
            executableIds.length}{" "}
          个 · 筛选外 {selected.filter((task) => !visibleIds.includes(task.id)).length}{" "}
          个
        </span>
      </div>
      <div>
        <button
          className="secondary-button"
          disabled={saving || !executableIds.length}
          onClick={onApply}
        >
          {archived ? <ArrowCounterClockwise size={17} /> : <Archive size={17} />}
          {archived ? "恢复" : "归档"}当前列表 {executableIds.length} 项
        </button>
        <button className="secondary-button" disabled={saving} onClick={onClear}>
          取消选择
        </button>
      </div>
      <details className="task-selection-details">
        <summary>查看已选任务</summary>
        <ul>
          {selected.map((task) => (
            <li key={task.id}>
              <div>
                <b>{task.title}</b>
                <code>{task.id}</code>
                <small>
                  {visibleIds.includes(task.id)
                    ? executableIds.includes(task.id)
                      ? "当前列表可操作"
                      : "当前列表不可操作"
                    : "筛选外，不参与本次操作"}
                </small>
              </div>
              <button
                className="text-button"
                disabled={saving}
                onClick={() => onRemove(task.id)}
                aria-label={`取消选择任务 ${task.id}`}
              >
                取消选择
              </button>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
