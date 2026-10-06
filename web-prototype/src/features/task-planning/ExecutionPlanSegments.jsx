import { ArrowDown, ArrowLineUp, ArrowUp } from "@phosphor-icons/react";
import { classNames } from "../../lib/presentation";
import { moveSegmentKey } from "../task-runtime/taskSegmentPolicy";

/** @typedef {import("./taskPlanContracts").TaskPlanSegment} TaskPlanSegment */
/** @typedef {{segment: TaskPlanSegment, executableKeys: string[], executableIndex: number, applyExecutableOrder: (keys: string[]) => void}} SegmentOrderProps */

/** @param {{orderedSegments: TaskPlanSegment[], onSegmentOrderChange?: (keys: string[]) => void}} props */
export function ExecutionPlanSegments({ orderedSegments, onSegmentOrderChange }) {
  const executableKeys = orderedSegments
    .filter((segment) => segment.status !== "blocked")
    .map((segment) => segment.segment_key);
  const blockedKeys = orderedSegments
    .filter((segment) => segment.status === "blocked")
    .map((segment) => segment.segment_key);
  /** @param {string[]} keys */
  const applyExecutableOrder = (keys) => {
    onSegmentOrderChange?.([...keys, ...blockedKeys]);
  };
  return (
    <div className="plan-segments">
      {orderedSegments.map((segment) => (
        <TaskPlanSegmentCard
          key={segment.segment_key}
          segment={segment}
          executableKeys={executableKeys}
          executableIndex={executableKeys.indexOf(segment.segment_key)}
          applyExecutableOrder={applyExecutableOrder}
          onSegmentOrderChange={onSegmentOrderChange}
        />
      ))}
    </div>
  );
}

/** @param {SegmentOrderProps & {onSegmentOrderChange?: (keys: string[]) => void}} props */
function TaskPlanSegmentCard({
  segment,
  executableKeys,
  executableIndex,
  applyExecutableOrder,
  onSegmentOrderChange,
}) {
  const canOrder = Boolean(onSegmentOrderChange) && executableIndex >= 0;
  return (
    <article
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
        const sourceKey = event.dataTransfer.getData("text/plain");
        applyExecutableOrder(
          moveSegmentKey(executableKeys, sourceKey, executableIndex),
        );
      }}
    >
      <TaskPlanSegmentInfo segment={segment} executableIndex={executableIndex} />
      {canOrder && executableKeys.length > 1 && (
        <TaskPlanOrderActions
          segment={segment}
          executableKeys={executableKeys}
          executableIndex={executableIndex}
          applyExecutableOrder={applyExecutableOrder}
        />
      )}
    </article>
  );
}

/** @param {{segment: TaskPlanSegment, executableIndex: number}} props */
function TaskPlanSegmentInfo({ segment, executableIndex }) {
  return (
    <>
      <div>
        <span>{segment.status === "blocked" ? "阻断" : "可执行"}</span>
        <h4>
          {executableIndex >= 0
            ? `${String(executableIndex + 1).padStart(2, "0")} · `
            : ""}
          {segment.scope?.listing
            ? `${segment.scope.listing} · ${segment.standard_name || segment.agent_family}`
            : segment.standard_name || segment.agent_family}
        </h4>
        <p>
          {segment.scope?.store
            ? `${segment.scope.store} / ${segment.scope.listing || "未识别 Listing"} · `
            : ""}
          {segment.standard_version ? `标准 V${segment.standard_version} · ` : ""}
          logic {segment.logic_version || "—"} · taxonomy {segment.taxonomy_version}
        </p>
      </div>
      <strong>
        {segment.record_count.toLocaleString()} 条 /{" "}
        {segment.unique_comments.toLocaleString()} 评论
      </strong>
      <ul>
        {segment.variants.map((variant) => (
          <li key={`${variant.category_a}-${variant.category_b}`}>
            {variant.category_a || "缺失品类A"} / {variant.category_b || "缺失品类B"}
          </li>
        ))}
      </ul>
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
      <span>拖拽或使用按钮调整</span>
    </div>
  );
}
