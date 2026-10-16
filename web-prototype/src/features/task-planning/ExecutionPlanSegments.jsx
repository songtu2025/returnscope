import { useState } from "react";
import { TaskPlanOrderActions } from "./TaskPlanOrderActions";
import { TaskPlanTableToolbar } from "./TaskPlanTableToolbar";
import { PlanSegmentDataDialog } from "./PlanSegmentDataDialog";
import {
  filterPlanSegments,
  applyVisibleOrder,
  listingKey,
} from "./taskPlanTablePolicy";
import { classNames } from "../../lib/presentation";
import { moveSegmentKey } from "../task-runtime/taskSegmentPolicy";

/** @typedef {import("./taskPlanContracts").TaskPlanSegment} TaskPlanSegment */
/** @typedef {{segment: TaskPlanSegment, executableKeys: string[], executableIndex: number, applyExecutableOrder: (keys: string[]) => void}} SegmentOrderProps */

/** @param {{orderedSegments: TaskPlanSegment[], onSegmentOrderChange?: (keys: string[]) => void, segmentSelection?: import("./taskPlanContracts").TaskSegmentSelection, onRecheck?: () => void | Promise<unknown>, defaultOrder?: string[], previewInput?: import("./taskPlanContracts").TaskPlanPreviewInput}} props */
export function ExecutionPlanSegments({
  orderedSegments,
  onSegmentOrderChange,
  segmentSelection,
  defaultOrder,
  previewInput,
  onRecheck,
}) {
  const [filters, setFilters] = useState({ query: "", category: "", status: "" });
  const [previewSegment, setPreviewSegment] = useState(
    /** @type {TaskPlanSegment | null} */ (null),
  );
  const visible = filterPlanSegments(orderedSegments, filters);
  const visibleKeys = visible
    .filter((item) => item.status !== "blocked")
    .map((item) => item.segment_key);
  const visibleListingKeys = new Set(visible.map(listingKey));
  const selectable = orderedSegments.filter((item) =>
    visibleListingKeys.has(listingKey(item)),
  );
  const visibleSelected = selectable.filter((item) =>
    segmentSelection?.keys.includes(item.segment_key),
  );
  const filtered = Boolean(filters.query || filters.category || filters.status);
  const executableKeys = orderedSegments
    .filter((item) => item.status !== "blocked")
    .map((item) => item.segment_key);
  const blockedKeys = orderedSegments
    .filter((item) => item.status === "blocked")
    .map((item) => item.segment_key);
  const chosen = orderedSegments.filter(
    (item) => !segmentSelection || segmentSelection.keys.includes(item.segment_key),
  );
  const listingCount = (/** @type {TaskPlanSegment[]} */ items) =>
    new Set(items.map(listingKey)).size;
  const chosenCount = chosen
    .filter((item) => item.status !== "blocked")
    .reduce((total, item) => total + item.unique_comments, 0);
  return (
    <div className="plan-segments">
      {segmentSelection && (
        <p className="plan-selection-summary" role="status">
          已选 {listingCount(chosen)} / {listingCount(orderedSegments)} 个 Listing ·{" "}
          {chosenCount.toLocaleString()} 组待分析评论
        </p>
      )}
      <TaskPlanTableToolbar
        segments={orderedSegments}
        filters={filters}
        onFilter={setFilters}
        onResetOrder={
          defaultOrder && onSegmentOrderChange
            ? () => onSegmentOrderChange(defaultOrder)
            : undefined
        }
      />
      <p className="plan-visible-count">
        当前显示 {visible.length} / {orderedSegments.length} 个分组
      </p>
      <div
        className="plan-segments-scroll"
        tabIndex={0}
        aria-label="执行分组表格，可横向滚动"
      >
        <table aria-label="分析范围及执行顺序">
          <thead>
            <tr>
              {segmentSelection && (
                <th>
                  <label className="plan-selection-cell">
                    <input
                      disabled={!selectable.length}
                      type="checkbox"
                      aria-label={
                        filtered ? "选择当前筛选 Listing" : "选择全部 Listing"
                      }
                      checked={
                        visibleSelected.length === selectable.length &&
                        selectable.length > 0
                      }
                      ref={(node) => {
                        if (node)
                          node.indeterminate =
                            visibleSelected.length > 0 &&
                            visibleSelected.length < selectable.length;
                      }}
                      onChange={() =>
                        segmentSelection.onChange(
                          visibleSelected.length === selectable.length
                            ? segmentSelection.keys.filter(
                                (key) =>
                                  !selectable.some((item) => item.segment_key === key),
                              )
                            : [
                                ...new Set([
                                  ...segmentSelection.keys,
                                  ...selectable.map((item) => item.segment_key),
                                ]),
                              ],
                        )
                      }
                    />
                  </label>
                </th>
              )}
              <th>顺序</th>
              <th>Listing / 店铺</th>
              <th>品类</th>
              <th>分类标准</th>
              <th className="number">源记录</th>
              <th className="number">评论组</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && (
              <tr>
                <td colSpan={segmentSelection ? 8 : 7}>
                  未找到匹配分组，请调整筛选条件。
                </td>
              </tr>
            )}
            {visible.map((segment) => (
              <TaskPlanSegmentRow
                key={segment.segment_key}
                segment={segment}
                executableKeys={visibleKeys}
                executableIndex={executableKeys.indexOf(segment.segment_key)}
                applyExecutableOrder={(keys) =>
                  onSegmentOrderChange?.(
                    filtered
                      ? applyVisibleOrder(
                          orderedSegments.map((item) => item.segment_key),
                          visibleKeys,
                          keys,
                        )
                      : [...keys, ...blockedKeys],
                  )
                }
                onSegmentOrderChange={onSegmentOrderChange}
                orderIndex={visibleKeys.indexOf(segment.segment_key)}
                onPreview={previewInput ? () => setPreviewSegment(segment) : undefined}
                selection={
                  segmentSelection && {
                    selected: segmentSelection.keys.includes(segment.segment_key),
                    toggle: () => {
                      const sameListing = orderedSegments
                        .filter((item) => listingKey(item) === listingKey(segment))
                        .map((item) => item.segment_key);
                      segmentSelection.onChange(
                        segmentSelection.keys.includes(segment.segment_key)
                          ? segmentSelection.keys.filter(
                              (key) => !sameListing.includes(key),
                            )
                          : [...new Set([...segmentSelection.keys, ...sameListing])],
                      );
                    },
                  }
                }
              />
            ))}
          </tbody>
        </table>
      </div>
      {previewSegment && previewInput && (
        <PlanSegmentDataDialog
          input={previewInput}
          onRecheck={onRecheck}
          segment={previewSegment}
          onClose={() => setPreviewSegment(null)}
        />
      )}
    </div>
  );
}

/** @param {SegmentOrderProps & {onSegmentOrderChange?: (keys: string[]) => void, selection?: {selected: boolean, toggle: () => void}, orderIndex: number, onPreview?: () => void}} props */
function TaskPlanSegmentRow({
  segment,
  executableKeys,
  executableIndex,
  applyExecutableOrder,
  onSegmentOrderChange,
  selection,
  orderIndex,
  onPreview,
}) {
  const canOrder = Boolean(onSegmentOrderChange) && executableIndex >= 0;
  return (
    <tr
      className={classNames(segment.status, canOrder && "is-orderable")}
      draggable={canOrder}
      onDragStart={(event) => {
        event.dataTransfer.setData("text/plain", segment.segment_key);
        event.dataTransfer.effectAllowed = "move";
      }}
      onDragOver={(event) => {
        if (canOrder) event.preventDefault();
      }}
      onDrop={(event) => {
        if (!canOrder) return;
        event.preventDefault();
        applyExecutableOrder(
          moveSegmentKey(
            executableKeys,
            event.dataTransfer.getData("text/plain"),
            orderIndex,
          ),
        );
      }}
    >
      {selection && (
        <td>
          <label className="plan-selection-cell">
            <input
              type="checkbox"
              aria-label={`选择 Listing：${segment.scope?.listing || segment.agent_family}`}
              checked={selection.selected}
              onChange={selection.toggle}
            />
          </label>
        </td>
      )}
      <td>
        {executableIndex >= 0 ? String(executableIndex + 1).padStart(2, "0") : "—"}
      </td>
      <TaskPlanSegmentInfo segment={segment} />
      <td>
        {onPreview && (
          <button type="button" className="text-button" onClick={onPreview}>
            查看数据
          </button>
        )}
        {canOrder && executableKeys.length > 1 && (
          <TaskPlanOrderActions
            segment={segment}
            executableKeys={executableKeys}
            executableIndex={orderIndex}
            applyExecutableOrder={applyExecutableOrder}
          />
        )}
      </td>
    </tr>
  );
}

/** @param {{segment: TaskPlanSegment}} props */
function TaskPlanSegmentInfo({ segment }) {
  return (
    <>
      <td>
        <h4>{segment.scope?.listing || segment.agent_family}</h4>
        <p>{segment.scope?.store || "—"}</p>
      </td>
      <td>
        {segment.variants.map((variant) => (
          <p key={`${variant.category_a}-${variant.category_b}`}>
            {variant.category_a || "缺失品类A"} / {variant.category_b || "缺失品类B"}
          </p>
        ))}
      </td>
      <td>
        <b>{segment.standard_name || segment.agent_family}</b>
        <p>
          <span className={`segment-status ${segment.status}`}>
            {segment.status === "blocked" ? "阻断" : "可执行"}
          </span>
          {segment.standard_version ? ` · V${segment.standard_version}` : ""}
        </p>
        <details>
          <summary>版本信息</summary>
          <p>logic {segment.logic_version || "—"}</p>
          <p>taxonomy {segment.taxonomy_version}</p>
        </details>
      </td>
      <td className="number">{segment.record_count.toLocaleString()} 条</td>
      <td className="number">{segment.unique_comments.toLocaleString()} 组</td>
    </>
  );
}
