import { useEffect, useRef, useState } from "react";
import Button from "antd/es/button";
import { X } from "@phosphor-icons/react";
import { useDialogFocus } from "../../hooks/useDialogFocus";
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
  const continueRef = useRef(/** @type {HTMLButtonElement | null} */ (null));
  const [labelQuery, setLabelQuery] = useState("");
  const [confirmClose, setConfirmClose] = useState(false);
  const editable = !readOnly && record.workflow_status === "pending";
  const draftSignature = JSON.stringify([
    mode,
    labelCode,
    reason,
    assessment,
    semanticItemReviews,
    addedSemanticItems,
    coverageStatus,
  ]);
  const initialDraft = useRef({ id: record.id, signature: draftSignature });
  const close = () => {
    if (saving) return;
    if (confirmClose) setConfirmClose(false);
    else if (editable && initialDraft.current.signature !== draftSignature)
      setConfirmClose(true);
    else onClose();
  };
  const { dialogRef: drawerRef } = useDialogFocus({ open: true, onClose: close });

  useEffect(() => {
    if (initialDraft.current.id !== record.id) {
      initialDraft.current = { id: record.id, signature: draftSignature };
      setLabelQuery("");
      setConfirmClose(false);
    }
  }, [record.id, draftSignature]);

  useEffect(() => {
    if (confirmClose) continueRef.current?.focus();
    else if (!drawerRef.current?.contains(document.activeElement))
      closeRef.current?.focus();
  }, [confirmClose, drawerRef]);

  useEffect(() => {
    // 保存和冲突刷新可能移除或禁用原控件，保留仍可操作的焦点。
    if (
      !saving &&
      (!drawerRef.current?.contains(document.activeElement) ||
        document.activeElement?.matches(":disabled"))
    ) {
      closeRef.current?.focus();
    }
  }, [record.id, conflict, saving, drawerRef]);

  return (
    <div className="review-drawer-layer">
      <aside
        ref={drawerRef}
        className="review-record-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-record-drawer-title"
        tabIndex={-1}
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
            data-dialog-initial-focus
            onClick={close}
          />
        </header>
        <div className="review-drawer-scroll">
          {confirmClose ? (
            <section className="review-conflict-panel" role="alert">
              <p>尚未保存的复核修改会丢失，是否放弃修改？</p>
              <div>
                <Button ref={continueRef} onClick={() => setConfirmClose(false)}>
                  继续编辑
                </Button>
                <Button danger onClick={onClose}>
                  放弃修改并关闭
                </Button>
              </div>
            </section>
          ) : (
            <>
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
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
