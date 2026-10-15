import { useState } from "react";

/** 复用未保存编辑的退出选择，只保留待执行动作，不保存业务资料。 */
export function useExitConfirmation() {
  const [pendingExit, setPendingExit] = useState(
    /** @type {{action: () => void} | null} */ (null),
  );
  const requestExit = (
    /** @type {boolean} */ dirty,
    /** @type {() => void} */ action,
  ) => {
    if (dirty) setPendingExit({ action });
    else action();
  };
  return {
    pendingExit,
    requestExit,
    discardChanges: () => {
      pendingExit?.action();
      setPendingExit(null);
    },
    continueEditing: () => setPendingExit(null),
  };
}
