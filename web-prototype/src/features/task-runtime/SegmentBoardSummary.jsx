import { ListBullets, WarningCircle } from "@phosphor-icons/react";
import { EmptyState } from "../../components/SharedUi";
import { navigateHash } from "../../app/hashRouter";

/** @param {{task: import("./taskRuntimeContracts").AnalysisTask, excludedCount: number}} props */
export function EmptyListingsSummary({ task, excludedCount }) {
  const removedCount = (task.segments ?? []).filter(
    (segment) => segment.deleted_at,
  ).length;
  const description = removedCount
    ? `本任务有 ${removedCount} 个 Listing 已移至回收站。入口按任务名称搜索，可能包含同名任务，请核对所属任务。`
    : excludedCount
      ? "当前数据均未纳入 Listing 执行，请查看下方的品类配置说明。"
      : "本任务尚无 Listing 执行项，可在“任务配置”页签核对分析范围。";
  return (
    <EmptyState
      icon={ListBullets}
      title="暂无可执行 Listing"
      description={description}
      action={
        removedCount > 0 && (
          <button
            type="button"
            className="secondary-button"
            onClick={() =>
              navigateHash("analysis-tasks", { view: "recycle", q: task.title })
            }
          >
            查看回收站
          </button>
        )
      }
    />
  );
}

/** @param {{keys: string[], selection?: ReturnType<typeof import("./useSegmentSelection").useSegmentSelection>, disabled: boolean}} props */
export function SegmentSelectionHeading({ keys, selection, disabled }) {
  const count = keys.filter((key) => selection?.keys.has(key)).length;
  return (
    <span className="listing-select-all">
      {selection && (
        <input
          className="listing-selection-checkbox"
          type="checkbox"
          aria-label="选择当前页 Listing"
          checked={keys.length > 0 && count === keys.length}
          ref={(node) => {
            if (node) node.indeterminate = count > 0 && count < keys.length;
          }}
          disabled={disabled || !keys.length}
          onChange={() => selection.toggle(keys)}
        />
      )}
      Listing
    </span>
  );
}

/** @param {{count: number}} props */
export function SegmentBoardHeader({ count }) {
  return (
    <div className="listing-queue-header">
      <div>
        <h3>
          Listing 明细 <span>{count}</span>
        </h3>
      </div>
    </div>
  );
}

/** @param {{count: number, excludedRecords: number, excludedComments: number}} props */
export function ExcludedListingsSummary({ count, excludedRecords, excludedComments }) {
  return (
    <>
      {count > 0 && (
        <div className="excluded-listing-summary">
          <WarningCircle size={18} />
          <div>
            <b>未配置品类的数据未纳入语义分析</b>
            <p>
              {excludedRecords.toLocaleString()} 条记录 /{" "}
              {excludedComments.toLocaleString()}
              组评论，不创建 Listing 执行项，也不会调用模型。
            </p>
          </div>
        </div>
      )}
    </>
  );
}
