import { useEffect, useRef, useState } from "react";
import { NAVIGATION_REQUEST_EVENT } from "../app/navigationGuard";
import { useExitConfirmation } from "./useExitConfirmation";

/** @param {{dirty: boolean, busy?: boolean, save: () => Promise<boolean>, discard?: () => void, canSave?: boolean, onRequest?: () => void}} options */
export function useUnsavedNavigation({
  dirty,
  busy = false,
  save,
  discard,
  canSave = true,
  onRequest,
}) {
  const exit = useExitConfirmation();
  const [savingExit, setSavingExit] = useState(false);
  const saveLock = useRef(false);
  const [failedSaveAttempt, setFailedSaveAttempt] = useState(0);
  const blocked = busy || savingExit;
  useEffect(() => {
    if (exit.pendingExit && !dirty && !blocked) exit.discardChanges();
  }, [blocked, dirty, exit]);
  useEffect(() => {
    if (!dirty && !blocked) return;
    const requestExit = (/** @type {Event} */ event) => {
      event.preventDefault();
      onRequest?.();
      const request = /** @type {CustomEvent<{proceed: () => void}>} */ (event);
      exit.requestExit(true, request.detail.proceed);
    };
    const beforeUnload = (/** @type {BeforeUnloadEvent} */ event) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener(NAVIGATION_REQUEST_EVENT, requestExit);
    window.addEventListener("beforeunload", beforeUnload);
    return () => {
      window.removeEventListener(NAVIGATION_REQUEST_EVENT, requestExit);
      window.removeEventListener("beforeunload", beforeUnload);
    };
  }, [blocked, dirty, exit, onRequest]);
  return {
    pendingExit: exit.pendingExit,
    busy: blocked,
    canSave,
    failedSaveAttempt,
    continueEditing: () => {
      if (!blocked && !saveLock.current) exit.continueEditing();
    },
    discardAndLeave: () => {
      if (blocked || saveLock.current) return;
      discard?.();
      exit.discardChanges();
    },
    saveAndLeave: async () => {
      if (blocked || saveLock.current || !canSave) return;
      saveLock.current = true;
      setSavingExit(true);
      try {
        if (await save()) exit.discardChanges();
        else setFailedSaveAttempt((attempt) => attempt + 1);
      } finally {
        saveLock.current = false;
        setSavingExit(false);
      }
    },
  };
}
