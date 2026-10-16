import { TaskPlanOrderActions } from "./TaskPlanOrderActions";
import { classNames } from "../../lib/presentation";
import { moveSegmentKey } from "../task-runtime/taskSegmentPolicy";

/** @typedef {import("./taskPlanContracts").TaskPlanSegment} TaskPlanSegment */
/** @typedef {{segment: TaskPlanSegment, executableKeys: string[], executableIndex: number, applyExecutableOrder: (keys: string[]) => void}} SegmentOrderProps */

/** @param {SegmentOrderProps & {onSegmentOrderChange?: (keys: string[]) => void, selection?: {selected: boolean, toggle: () => void}, orderIndex: number, onPreview?: () => void}} props */
export function TaskPlanSegmentRow({
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
              aria-label={`参与分析：${segment.scope?.listing || segment.agent_family}`}
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
