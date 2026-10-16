import { useState } from "react";
import { ArrowDown, ArrowLineUp, ArrowUp } from "@phosphor-icons/react";
import { moveSegmentKey } from "../task-runtime/taskSegmentPolicy";
/** @param {{segment: import("./taskPlanContracts").TaskPlanSegment, executableKeys: string[], executableIndex: number, applyExecutableOrder: (keys: string[]) => void}} props */
export function TaskPlanOrderActions({
  segment,
  executableKeys,
  executableIndex,
  applyExecutableOrder,
}) {
  const [position, setPosition] = useState("");
  const [error, setError] = useState("");
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
      <details className="plan-position-control">
        <summary>移至位置</summary>
        <label>
          当前筛选队列位置
          <input
            aria-label={`移动 ${segmentLabel} 到位置`}
            type="number"
            min="1"
            max={executableKeys.length}
            value={position}
            onChange={(event) => setPosition(event.target.value)}
          />
        </label>
        <button
          type="button"
          className="text-button"
          onClick={() => {
            const value = Number(position);
            if (
              !Number.isInteger(value) ||
              value < 1 ||
              value > executableKeys.length
            ) {
              setError(`请输入1到${executableKeys.length}的整数`);
              return;
            }
            applyExecutableOrder(
              moveSegmentKey(executableKeys, segment.segment_key, value - 1),
            );
            setError("");
          }}
        >
          移动
        </button>
        {error && <p role="alert">{error}</p>}
      </details>
    </div>
  );
}
