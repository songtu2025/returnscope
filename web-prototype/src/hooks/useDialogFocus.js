import { useEffect, useEffectEvent, useRef } from "react";

const DIALOG_CONTROL_SELECTOR =
  'button:not(:disabled), a[href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled), summary, [tabindex="0"]';

/** @type {HTMLElement[]} */
const dialogs = [];
const handledKeys = new WeakSet();
const topDialog = () => dialogs.filter((dialog) => dialog.isConnected).at(-1);

/** @param {HTMLElement | null} dialog @returns {HTMLElement[]} */
function dialogControls(dialog) {
  if (!dialog) return [];
  return [...dialog.querySelectorAll("*")]
    .filter((element) => element instanceof HTMLElement)
    .filter((element) => element.matches(DIALOG_CONTROL_SELECTOR))
    .filter((element) => element.closest('[role="dialog"]') === dialog)
    .filter((element) => {
      if (
        element.closest("[hidden]") ||
        element.getAttribute("aria-hidden") === "true"
      ) {
        return false;
      }
      if (element === document.activeElement) return true;
      /** @type {HTMLElement | null} */
      let current = element;
      while (current && current !== dialog) {
        const style = window.getComputedStyle(current);
        if (style.display === "none" || style.visibility === "hidden") return false;
        current = current.parentElement;
      }
      return (
        typeof element.checkVisibility !== "function" ||
        element.checkVisibility({ checkOpacity: false })
      );
    });
}

/** @param {KeyboardEvent | import("react").KeyboardEvent} event @param {HTMLElement | null} dialog */
function constrainDialogFocus(event, dialog) {
  if (
    event.key !== "Tab" ||
    !dialog ||
    topDialog() !== dialog ||
    event.defaultPrevented
  )
    return;
  const native = "nativeEvent" in event ? event.nativeEvent : event;
  if (handledKeys.has(native)) return;
  handledKeys.add(native);
  const controls = dialogControls(dialog);
  const first = controls[0];
  const last = controls.at(-1);
  if (!first) {
    event.preventDefault();
    dialog.focus();
  } else if (!dialog.contains(document.activeElement)) {
    event.preventDefault();
    first.focus();
  } else if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last?.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

/** @param {{open: boolean, onClose: () => void, returnFocusRef?: {current: HTMLElement | null}}} options */
export function useDialogFocus({ open, onClose, returnFocusRef }) {
  const dialogRef = useRef(/** @type {HTMLElement | null} */ (null));
  const closeRef = useRef(onClose);
  const currentReturnTarget = useEffectEvent(() => returnFocusRef?.current);

  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return undefined;
    const previousFocus = returnFocusRef?.current ?? document.activeElement;
    const dialog = dialogRef.current;
    if (!dialog) return undefined;
    // 同时挂载的嵌套弹窗先执行子层 effect，父层应插在子层前面。
    const childIndex = dialogs.findIndex((item) => dialog.contains(item));
    dialogs.splice(childIndex < 0 ? dialogs.length : childIndex, 0, dialog);
    const initialFocus =
      dialog?.querySelector("[data-dialog-initial-focus]") ??
      dialogControls(dialog)[0] ??
      dialog;
    if (topDialog() === dialog && initialFocus instanceof HTMLElement)
      initialFocus.focus();

    /** @param {KeyboardEvent} event */
    const handleKeyDown = (event) => {
      if (
        topDialog() !== dialog ||
        event.defaultPrevented ||
        event.isComposing ||
        event.keyCode === 229
      )
        return;
      if (event.key === "Escape") {
        if (handledKeys.has(event)) return;
        handledKeys.add(event);
        event.preventDefault();
        closeRef.current();
        return;
      }
      constrainDialogFocus(event, dialogRef.current);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      const wasTop = topDialog() === dialog || dialogs.at(-1) === dialog;
      dialogs.splice(dialogs.indexOf(dialog), 1);
      if (!wasTop) return;
      const next = topDialog();
      const returnTarget = currentReturnTarget() ?? previousFocus;
      if (
        returnTarget instanceof HTMLElement &&
        returnTarget.isConnected &&
        (!next || next.contains(returnTarget))
      ) {
        returnTarget.focus();
      } else if (next) {
        (dialogControls(next)[0] ?? next).focus();
      }
    };
  }, [open, returnFocusRef]);

  return {
    dialogRef,
    constrainFocus: (/** @type {import("react").KeyboardEvent} */ event) =>
      constrainDialogFocus(event, dialogRef.current),
  };
}
