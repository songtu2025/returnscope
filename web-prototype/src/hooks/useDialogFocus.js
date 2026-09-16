import { useEffect, useRef } from "react";

const DIALOG_CONTROL_SELECTOR =
  'button:not(:disabled), a[href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled), summary, [tabindex="0"]';

/** @param {HTMLElement | null} dialog @returns {HTMLElement[]} */
function dialogControls(dialog) {
  if (!dialog) return [];
  return [...dialog.querySelectorAll("*")]
    .filter((element) => element instanceof HTMLElement)
    .filter((element) => element.matches(DIALOG_CONTROL_SELECTOR))
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
  if (event.key !== "Tab" || !dialog) return;
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

/** @param {{open: boolean, onClose: () => void}} options */
export function useDialogFocus({ open, onClose }) {
  const dialogRef = useRef(/** @type {HTMLElement | null} */ (null));
  const closeRef = useRef(onClose);

  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return undefined;
    const previousFocus = document.activeElement;
    const dialog = dialogRef.current;
    const initialFocus =
      dialog?.querySelector("[data-dialog-initial-focus]") ??
      dialogControls(dialog)[0] ??
      dialog;
    if (initialFocus instanceof HTMLElement) initialFocus.focus();

    /** @param {KeyboardEvent} event */
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeRef.current();
        return;
      }
      constrainDialogFocus(event, dialogRef.current);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) {
        previousFocus.focus();
      }
    };
  }, [open]);

  return {
    dialogRef,
    constrainFocus: (/** @type {import("react").KeyboardEvent} */ event) =>
      constrainDialogFocus(event, dialogRef.current),
  };
}
