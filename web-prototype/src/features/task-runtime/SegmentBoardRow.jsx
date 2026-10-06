import { SegmentBoardCells } from "./SegmentBoardCells";
import { SegmentPrimaryActions } from "./SegmentPrimaryActions";
import { classNames } from "../../lib/presentation";
import { moveSegmentKey } from "./taskSegmentPolicy";
import { SegmentBoardDetail } from "./SegmentBoardDetail";
import {
  segmentOrderPosition,
  segmentResultPresentation,
} from "./segmentBoardRowPolicy";

/** @typedef {import("./segmentBoardRowContracts").SegmentBoardRowProps} SegmentBoardRowProps */

/** @param {SegmentBoardRowProps} props */
export function SegmentBoardRow({ task, segment, position, queue, rowState, actions }) {
  const { focusSegmentId, focusedSegmentRef } = position;
  const { orderableKeys, reordering, applyOrder } = queue;
  const { expandedSegmentKey } = rowState;
  const isFocused =
    Boolean(focusSegmentId) &&
    [segment.id, segment.segment_key].some(
      (value) => String(value) === String(focusSegmentId),
    );
  const { orderableIndex, canOrder } = segmentOrderPosition(segment, queue);
  const presentation = segmentResultPresentation(segment);

  return (
    <article
      ref={isFocused ? focusedSegmentRef : null}
      draggable={canOrder && !reordering && expandedSegmentKey === segment.segment_key}
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
        applyOrder(moveSegmentKey(orderableKeys, sourceKey, orderableIndex));
      }}
      className={classNames(
        "listing-row",
        segment.error && "has-error",
        canOrder && "is-orderable",
        isFocused && "is-targeted",
      )}
      aria-current={isFocused ? "true" : undefined}
      role="row"
    >
      <SegmentBoardCells
        task={task}
        segment={segment}
        position={position}
        presentation={presentation}
        primaryActions={
          <SegmentPrimaryActions
            task={task}
            segment={segment}
            rowState={rowState}
            actions={actions}
            publishStatus={presentation.publishStatus}
          />
        }
      />
      {expandedSegmentKey === segment.segment_key && (
        <SegmentBoardDetail
          task={task}
          segment={segment}
          canOrder={canOrder}
          orderableIndex={orderableIndex}
          queue={queue}
          actions={actions}
          stateDescription={presentation.stateDescription}
          stateLabel={presentation.stateLabel}
        />
      )}
    </article>
  );
}
