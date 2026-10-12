import { useRef, useState } from "react";
/** @typedef {() => void} ExitAction */

/** 仅在内存中保留编辑基线，密钥不写入浏览器存储。 */
export function useModelServiceEditing() {
  const baseline = useRef("");
  const [touched, setTouched] = useState(/** @type {string[]} */ ([]));
  const [pendingExit, setPendingExit] = useState(
    /** @type {{action: ExitAction} | null} */ (null),
  );
  const reset = (/** @type {unknown} */ value) => {
    baseline.current = JSON.stringify(value);
    setTouched([]);
  };
  const isDirty = (/** @type {unknown} */ value) =>
    baseline.current !== JSON.stringify(value);
  const requestExit = (
    /** @type {boolean} */ dirty,
    /** @type {() => void} */ action,
  ) => {
    if (dirty) setPendingExit({ action });
    else action();
  };
  const discardChanges = () => {
    pendingExit?.action();
    setPendingExit(null);
  };
  const touch = (/** @type {string} */ field) =>
    setTouched((current) => (current.includes(field) ? current : [...current, field]));
  return {
    reset,
    isDirty,
    touched,
    touch,
    pendingExit,
    requestExit,
    discardChanges,
    continueEditing: () => setPendingExit(null),
  };
}
