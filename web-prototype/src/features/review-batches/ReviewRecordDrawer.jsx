import { useRef } from "react";
import Button from "antd/es/button";
import { X } from "@phosphor-icons/react";
import { useDialogFocus } from "../../hooks/useDialogFocus";
import { ReviewRecordEvidence } from "./ReviewRecordEvidence";
import { values, valueText } from "./reviewRecordPresentation";
import {
  addedSemanticItemDrafts,
  semanticItemReviewDrafts,
} from "./reviewRecordDrafts";

/** @param {Pick<import("./reviewRecordPresentation").ReviewRecordDrawerProps, "record" | "labels" | "onClose">} props */
export function ReviewRecordDrawer({ record, labels, onClose }) {
  const triggerRef = useRef(
    /** @type {HTMLElement | null} */ (
      document.activeElement instanceof HTMLElement ? document.activeElement : null
    ),
  );
  const { dialogRef } = useDialogFocus({
    open: true,
    onClose,
    returnFocusRef: triggerRef,
  });
  return (
    <div className="review-drawer-layer">
      <aside
        ref={dialogRef}
        className="review-record-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-record-drawer-title"
        tabIndex={-1}
      >
        <header>
          <div>
            <span>历史复核记录</span>
            <h2 id="review-record-drawer-title">
              {valueText(values(record, "order_ids"))}
            </h2>
          </div>
          <Button
            type="text"
            icon={<X size={20} />}
            aria-label="关闭复核抽屉"
            data-dialog-initial-focus
            onClick={onClose}
          />
        </header>
        <div className="review-drawer-scroll">
          <ReviewRecordEvidence
            record={record}
            labels={labels}
            semanticItemReviews={semanticItemReviewDrafts(record.classification)}
            addedSemanticItems={addedSemanticItemDrafts(record.classification)}
            coverageStatus={
              record.classification?.coverage_review?.status || "complete"
            }
          />
        </div>
      </aside>
    </div>
  );
}
