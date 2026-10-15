import { useRef, useState } from "react";
import { useExitConfirmation } from "../../hooks/useExitConfirmation";

/** 仅在内存中保留编辑基线，密钥不写入浏览器存储。 */
export function useModelServiceEditing() {
  const baseline = useRef("");
  const [touched, setTouched] = useState(/** @type {string[]} */ ([]));
  const exit = useExitConfirmation();
  const reset = (/** @type {unknown} */ value) => {
    baseline.current = JSON.stringify(value);
    setTouched([]);
  };
  const isDirty = (/** @type {unknown} */ value) =>
    baseline.current !== JSON.stringify(value);
  const touch = (/** @type {string} */ field) =>
    setTouched((current) => (current.includes(field) ? current : [...current, field]));
  return {
    reset,
    isDirty,
    touched,
    touch,
    ...exit,
  };
}
