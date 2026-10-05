import { useEffect, useRef, useState } from "react";
import Button from "antd/es/button";
import { X } from "@phosphor-icons/react";
import { ReviewRecordEvidence } from "./ReviewRecordEvidence";
import { ReviewRecordEditor } from "./ReviewRecordEditor";
import { values, valueText } from "./reviewRecordPresentation";

/**
 * @param {import("./reviewRecordPresentation").ReviewRecordDrawerProps} props
 */
export function ReviewRecordDrawer({
  record,
  readOnly,
  labels,
  mode,
  labelCode,
  reason,
  conflict,
  saving,
  assessment,
  semanticItemReviews,
  addedSemanticItems,
  coverageStatus,
  onMode,
  onAssessment,
  onSemanticItemReviews,
  onAddedSemanticItems,
  onCoverageStatus,
  onLabelCode,
  onReason,
  onSave,
  onSaveAndNext,
  onClose,
  onUseServer,
  onContinueWithServer,
}) {
  const closeRef = useRef(/** @type {HTMLButtonElement | null} */ (null));
  const drawerRef = useRef(/** @type {HTMLElement | null} */ (null));
  const onCloseRef = useRef(onClose);
  const [labelQuery, setLabelQuery] = useState("");
  const editable = !readOnly && record.workflow_status === "pending";

  useEffect(() => {
    setLabelQuery("");
  }, [record.id]);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const returnFocus =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeRef.current?.focus();
    /** @param {KeyboardEvent} event */
    const handleKey = (event) => {
      if (event.key === "Escape") {
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        /** @type {NodeListOf<HTMLElement>} */ (
          drawerRef.current?.querySelectorAll(
            'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
          ) ?? []
        ),
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("keydown", handleKey);
      returnFocus?.focus();
    };
  }, []);

  return (
    <div className="review-drawer-layer">
      <aside
        ref={drawerRef}
        className="review-record-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-record-drawer-title"
      >
        <header>
          <div>
            <span>{editable ? "处理复核记录" : "查看复核记录"}</span>
            <h2 id="review-record-drawer-title">
              {valueText(values(record, "order_ids"))}
            </h2>
          </div>
          <Button
            ref={closeRef}
            type="text"
            icon={<X size={20} />}
            aria-label="关闭复核抽屉"
            onClick={onClose}
          />
        </header>
        <div className="review-drawer-scroll">
          <ReviewRecordEvidence
            record={record}
            labels={labels}
            editable={editable}
            semanticItemReviews={semanticItemReviews}
            addedSemanticItems={addedSemanticItems}
            coverageStatus={coverageStatus}
            onSemanticItemReviews={onSemanticItemReviews}
            onAddedSemanticItems={onAddedSemanticItems}
            onCoverageStatus={onCoverageStatus}
          />
          <ReviewRecordEditor
            labels={labels}
            editable={editable}
            mode={mode}
            labelCode={labelCode}
            reason={reason}
            conflict={conflict}
            saving={saving}
            assessment={assessment}
            labelQuery={labelQuery}
            onLabelQuery={setLabelQuery}
            onMode={onMode}
            onAssessment={onAssessment}
            onLabelCode={onLabelCode}
            onReason={onReason}
            onSave={onSave}
            onSaveAndNext={onSaveAndNext}
            onUseServer={onUseServer}
            onContinueWithServer={onContinueWithServer}
          />
        </div>
      </aside>
    </div>
  );
}
