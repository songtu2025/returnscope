import { useDismissibleDetails } from "../../hooks/useDismissibleDetails";
import { MagnifyingGlass } from "@phosphor-icons/react";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/**
 * @typedef {Object} ParallelismState
 * @property {boolean} changingParallelism
 * @property {import("react").Dispatch<import("react").SetStateAction<boolean>>} setChangingParallelism
 * @property {boolean} canManageQueue
 * @property {number} maxParallelSegments
 * @property {number} ownerRunningSegments
 * @property {(value: number) => Promise<unknown>} onParallelism
 */

/** @param {{task: AnalysisTask, parallelism: ParallelismState}} props */
function ParallelismSettings({ task, parallelism }) {
  const {
    changingParallelism,
    setChangingParallelism,
    canManageQueue,
    maxParallelSegments,
    ownerRunningSegments,
    onParallelism,
  } = parallelism;
  const { detailsProps, summaryProps } = useDismissibleDetails();
  return (
    <details {...detailsProps} className="listing-execution-settings">
      <summary {...summaryProps}>执行设置</summary>
      <div className="parallelism-control" aria-label="Listing 并行数">
        <span>运行配额</span>
        <b>
          {ownerRunningSegments}/{task.owner_segment_limit ?? 3}
        </b>
        <span className="parallelism-divider" />
        <span>并行数</span>
        <button
          type="button"
          className="icon-button"
          disabled={changingParallelism || !canManageQueue || maxParallelSegments <= 1}
          aria-label="减少 Listing 并行数"
          onClick={async () => {
            setChangingParallelism(true);
            await onParallelism(maxParallelSegments - 1);
            setChangingParallelism(false);
          }}
        >
          −
        </button>
        <b>{maxParallelSegments}</b>
        <button
          type="button"
          className="icon-button"
          disabled={changingParallelism || !canManageQueue || maxParallelSegments >= 3}
          aria-label="增加 Listing 并行数"
          onClick={async () => {
            setChangingParallelism(true);
            await onParallelism(maxParallelSegments + 1);
            setChangingParallelism(false);
          }}
        >
          +
        </button>
      </div>
    </details>
  );
}

/**
 * @param {{task: AnalysisTask, query: string, statusFilter: string,
 * setQuery: import("react").Dispatch<import("react").SetStateAction<string>>,
 * setStatusFilter: import("react").Dispatch<import("react").SetStateAction<string>>,
 * parallelism: ParallelismState}} props
 */
export function SegmentBoardToolbar({
  task,
  query,
  statusFilter,
  setQuery,
  setStatusFilter,
  parallelism,
}) {
  return (
    <div className="listing-queue-toolbar">
      <div className="listing-queue-filters">
        <label className="listing-queue-search">
          <MagnifyingGlass size={17} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索 Listing（编号 / 站点 / 标准）"
            aria-label="搜索 Listing"
          />
        </label>
        <select
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
          aria-label="按 Listing 状态筛选"
        >
          <option value="all">全部状态</option>
          <option value="active">未结束</option>
          <option value="attention">需处理</option>
          <option value="delivered">已生成结果</option>
          <option value="cancelled">已取消</option>
        </select>
      </div>
      <ParallelismSettings task={task} parallelism={parallelism} />
    </div>
  );
}
