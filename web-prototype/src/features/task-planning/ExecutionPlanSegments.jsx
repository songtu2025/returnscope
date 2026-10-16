import { ArrowDown, ArrowLineUp, ArrowUp } from "@phosphor-icons/react";
import { classNames } from "../../lib/presentation";
import { moveSegmentKey } from "../task-runtime/taskSegmentPolicy";

/** @typedef {import("./taskPlanContracts").TaskPlanSegment} TaskPlanSegment */
/** @typedef {{segment: TaskPlanSegment, executableKeys: string[], executableIndex: number, applyExecutableOrder: (keys: string[]) => void}} SegmentOrderProps */

/** @param {TaskPlanSegment} item */
const listingKey = (item) =>
  JSON.stringify(
    item.scope ? [item.scope.store, item.scope.listing] : item.segment_key,
  );

/** @param {{orderedSegments: TaskPlanSegment[], onSegmentOrderChange?: (keys: string[]) => void, segmentSelection?: import("./taskPlanContracts").TaskSegmentSelection}} props */
export function ExecutionPlanSegments({
  orderedSegments,
  onSegmentOrderChange,
  segmentSelection,
}) {
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
                      type="checkbox"
                      aria-label="选择全部 Listing"
                      checked={
                        chosen.length === orderedSegments.length && chosen.length > 0
                      }
                      ref={(node) => {
                        if (node)
                          node.indeterminate =
                            chosen.length > 0 && chosen.length < orderedSegments.length;
                      }}
                      onChange={() =>
                        segmentSelection.onChange(
                          chosen.length === orderedSegments.length
                            ? []
                            : orderedSegments.map((item) => item.segment_key),
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
              <th>顺序调整</th>
            </tr>
          </thead>
          <tbody>
            {orderedSegments.map((segment) => (
              <TaskPlanSegmentRow
                key={segment.segment_key}
                segment={segment}
                executableKeys={executableKeys}
                executableIndex={executableKeys.indexOf(segment.segment_key)}
                applyExecutableOrder={(keys) =>
                  onSegmentOrderChange?.([...keys, ...blockedKeys])
                }
                onSegmentOrderChange={onSegmentOrderChange}
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
    </div>
  );
}

/** @param {SegmentOrderProps & {onSegmentOrderChange?: (keys: string[]) => void, selection?: {selected: boolean, toggle: () => void}}} props */
function TaskPlanSegmentRow({
  segment,
  executableKeys,
  executableIndex,
  applyExecutableOrder,
  onSegmentOrderChange,
  selection,
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
            executableIndex,
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
        {canOrder && executableKeys.length > 1 && (
          <TaskPlanOrderActions
            segment={segment}
            executableKeys={executableKeys}
            executableIndex={executableIndex}
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

/** @param {SegmentOrderProps} props */
function TaskPlanOrderActions({
  segment,
  executableKeys,
  executableIndex,
  applyExecutableOrder,
}) {
  const segmentLabel = segment.scope?.listing || segment.agent_family;
  /** @type {readonly (readonly [string, import("react").ElementType, number, boolean])[]} */
  const actions = [
    ["置顶", ArrowLineUp, 0, executableIndex === 0],
    ["上移", ArrowUp, executableIndex - 1, executableIndex === 0],
    [
      "下移",
      ArrowDown,
      executableIndex + 1,
      executableIndex === executableKeys.length - 1,
    ],
  ];
  return (
    <div className="segment-order-actions">
      {actions.map(([label, Icon, targetIndex, disabled]) => (
        <button
          key={label}
          type="button"
          aria-label={`${label} ${segmentLabel}`}
          title={label}
          disabled={disabled}
          onClick={() =>
            applyExecutableOrder(
              moveSegmentKey(executableKeys, segment.segment_key, targetIndex),
            )
          }
        >
          <Icon size={15} />
        </button>
      ))}
    </div>
  );
}
