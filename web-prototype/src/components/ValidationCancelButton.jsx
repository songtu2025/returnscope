import { useState } from "react";
import { cancelValidation } from "../shared/api/validationCancellation";
import { errorMessage } from "../shared/api/requestErrors";

/** @param {{kind: "model" | "standard", id: string, onChanged?: () => void | Promise<void>}} props */
export function ValidationCancelButton({ kind, id, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const cancel = async () => {
    setBusy(true);
    setError("");
    try {
      await cancelValidation(kind, id);
      await onChanged?.();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div>
      <button className="secondary-button" disabled={busy} onClick={cancel}>
        {busy ? "取消中…" : "取消本次验证"}
      </button>
      {error && <span role="alert">{error}</span>}
    </div>
  );
}
