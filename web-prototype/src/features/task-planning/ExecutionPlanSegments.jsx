import { useState } from "react";
import { TaskPlanSegmentRow } from "./TaskPlanSegmentRow";
import { TaskPlanTableToolbar } from "./TaskPlanTableToolbar";
import { PlanSegmentDataDialog } from "./PlanSegmentDataDialog";
import { Pagination } from "../../components/Pagination";
import {
  filterPlanSegments,
  applyVisibleOrder,
  listingKey,
  paginatePlanListings,
  selectPlanSegments,
} from "./taskPlanTablePolicy";

/** @typedef {import("./taskPlanContracts").TaskPlanSegment} TaskPlanSegment */

/** @param {{orderedSegments: TaskPlanSegment[], onSegmentOrderChange?: (keys: string[]) => void, segmentSelection?: import("./taskPlanContracts").TaskSegmentSelection, onRecheck?: () => void | Promise<unknown>, defaultOrder?: string[], previewInput?: import("./taskPlanContracts").TaskPlanPreviewInput}} props */
export function ExecutionPlanSegments({
  orderedSegments,
  onSegmentOrderChange,
  segmentSelection,
  defaultOrder,
  previewInput,
  onRecheck,
}) {
  const [ordering, setOrdering] = useState(!segmentSelection);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [filters, setFilters] = useState({ query: "", category: "", status: "" });
  const [previewSegment, setPreviewSegment] = useState(
    /** @type {TaskPlanSegment | null} */ (null),
  );
  const visible = filterPlanSegments(orderedSegments, filters);
  const paginated = paginatePlanListings(
    visible,
    segmentSelection ? page : 1,
    segmentSelection ? pageSize : visible.length || 1,
  );
  const visibleKeys = visible
    .filter((item) => item.status !== "blocked")
    .map((item) => item.segment_key);
  const visibleListingKeys = new Set(visible.map(listingKey));
  const selectable = orderedSegments.filter((item) =>
    visibleListingKeys.has(listingKey(item)),
  );
  const pageListings = new Set(paginated.items.map(listingKey));
  const pageSelectable = selectable.filter((item) =>
    pageListings.has(listingKey(item)),
  );
  const pageSelected = pageSelectable.filter((item) =>
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
        onFilter={(value) => {
          setFilters(value);
          setPage(1);
        }}
        rangeSelection={
          segmentSelection
            ? {
                total: paginated.total,
                filtered,
                onChange: (selected) =>
                  segmentSelection.onChange(
                    selectPlanSegments(segmentSelection.keys, selectable, selected),
                  ),
              }
            : undefined
        }
        ordering={ordering}
        onToggleOrder={
          onSegmentOrderChange ? () => setOrdering((value) => !value) : undefined
        }
        onResetOrder={
          ordering && defaultOrder && onSegmentOrderChange
            ? () => onSegmentOrderChange(defaultOrder)
            : undefined
        }
      />
      <p className="plan-visible-count">
        当前筛选 {paginated.total} 个 Listing · 本页 {paginated.items.length} 个分组
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
                  <span>参与分析</span>
                  <label className="plan-selection-cell">
                    <input
                      disabled={!pageSelectable.length}
                      type="checkbox"
                      aria-label="本页全部参与"
                      checked={
                        pageSelected.length === pageSelectable.length &&
                        pageSelectable.length > 0
                      }
                      ref={(node) => {
                        if (node)
                          node.indeterminate =
                            pageSelected.length > 0 &&
                            pageSelected.length < pageSelectable.length;
                      }}
                      onChange={() =>
                        segmentSelection.onChange(
                          selectPlanSegments(
                            segmentSelection.keys,
                            pageSelectable,
                            pageSelected.length !== pageSelectable.length,
                          ),
                        )
                      }
                    />
                    <span>本页</span>
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
            {paginated.items.length === 0 && (
              <tr>
                <td colSpan={segmentSelection ? 8 : 7}>
                  未找到匹配分组，请调整筛选条件。
                </td>
              </tr>
            )}
            {paginated.items.map((segment) => (
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
                onSegmentOrderChange={ordering ? onSegmentOrderChange : undefined}
                orderIndex={visibleKeys.indexOf(segment.segment_key)}
                onPreview={previewInput ? () => setPreviewSegment(segment) : undefined}
                selection={
                  segmentSelection && {
                    selected: segmentSelection.keys.includes(segment.segment_key),
                    toggle: () => {
                      const sameListing = orderedSegments.filter(
                        (item) => listingKey(item) === listingKey(segment),
                      );
                      segmentSelection.onChange(
                        selectPlanSegments(
                          segmentSelection.keys,
                          sameListing,
                          !segmentSelection.keys.includes(segment.segment_key),
                        ),
                      );
                    },
                  }
                }
              />
            ))}
          </tbody>
        </table>
      </div>
      {segmentSelection && (
        <Pagination
          page={paginated.page}
          pageSize={pageSize}
          total={paginated.total}
          totalPages={paginated.totalPages}
          unit="个 Listing"
          onPage={setPage}
          onPageSize={(size) => {
            setPageSize(size);
            setPage(1);
          }}
        />
      )}
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
