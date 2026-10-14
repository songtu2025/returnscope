import { useState } from "react";
import { errorMessage } from "../shared/api/requestErrors";

/** @param {{onRestore: () => Promise<void>, disabled?: boolean}} props */
export function HistoryRestoreButton({ onRestore, disabled }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const restore = async () => {
    setBusy(true);
    setError("");
    try {
      await onRestore();
      setConfirming(false);
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="modal-actions">
      {confirming ? (
        <>
          <span>还原为此次修改前的内容，并保存新记录？</span>
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() => setConfirming(false)}
          >
            取消还原
          </button>
          <button
            className="primary-button"
            disabled={busy || disabled}
            onClick={restore}
          >
            {busy ? "还原中…" : "确认还原"}
          </button>
        </>
      ) : (
        <button
          className="secondary-button"
          disabled={disabled}
          onClick={() => setConfirming(true)}
        >
          还原此次修改
        </button>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
