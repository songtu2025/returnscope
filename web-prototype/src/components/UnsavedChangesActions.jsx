import { useEffect, useRef } from "react";
import { Modal } from "./SharedUi";

/** @param {{guard: ReturnType<typeof import("../hooks/useUnsavedNavigation").useUnsavedNavigation>, message?: string}} props */
export function UnsavedChangesActions({ guard, message = "离开前是否保存本次修改？" }) {
  const saveRef = useRef(/** @type {HTMLButtonElement | null} */ (null));
  const continueRef = useRef(/** @type {HTMLButtonElement | null} */ (null));
  useEffect(() => {
    continueRef.current?.focus({ preventScroll: true });
  }, []);
  useEffect(() => {
    if (guard.failedSaveAttempt > 0 && !guard.busy)
      saveRef.current?.focus({ preventScroll: true });
  }, [guard.failedSaveAttempt, guard.busy]);
  return (
    <section role="alert">
      <p>{message}</p>
      <div className="modal-actions">
        <button
          type="button"
          ref={continueRef}
          className="secondary-button"
          disabled={guard.busy}
          onClick={guard.continueEditing}
        >
          继续编辑
        </button>
        <button
          type="button"
          className="secondary-button"
          disabled={guard.busy}
          onClick={guard.discardAndLeave}
        >
          放弃修改并离开
        </button>
        <button
          type="button"
          ref={saveRef}
          className="primary-button"
          disabled={guard.busy || !guard.canSave}
          onClick={guard.saveAndLeave}
        >
          {guard.busy ? "保存中…" : "保存后离开"}
        </button>
      </div>
    </section>
  );
}

/** @param {{guard: ReturnType<typeof import("../hooks/useUnsavedNavigation").useUnsavedNavigation>, title?: string, message?: string}} props */
export function UnsavedChangesDialog({ guard, title = "修改尚未保存", message }) {
  return guard.pendingExit ? (
    <Modal title={title} onClose={guard.continueEditing}>
      <div className="modal-form">
        <UnsavedChangesActions guard={guard} message={message} />
      </div>
    </Modal>
  ) : null;
}
