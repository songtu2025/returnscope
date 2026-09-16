import { useEffect, useRef } from "react";

const DIALOG_CONTROL_SELECTOR =
  'button:not(:disabled), a[href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled), summary, [tabindex="0"]';

function dialogControls(dialog) {
  if (!dialog) return [];
  return [...dialog.querySelectorAll("*")]
    .filter((element) => element.matches(DIALOG_CONTROL_SELECTOR))
    .filter((element) => {
      if (
        element.closest("[hidden]") ||
        element.getAttribute("aria-hidden") === "true"
      ) {
        return false;
      }
      if (element === document.activeElement) return true;
      for (
        let current = element;
        current && current !== dialog;
        current = current.parentElement
      ) {
        const style = window.getComputedStyle(current);
        if (style.display === "none" || style.visibility === "hidden") return false;
      }
      return (
        typeof element.checkVisibility !== "function" ||
        element.checkVisibility({ checkOpacity: false })
      );
    });
}

function constrainDialogFocus(event, dialog) {
  if (event.key !== "Tab") return;
  const controls = dialogControls(dialog);
  const first = controls[0];
  const last = controls.at(-1);
  if (!first) {
    event.preventDefault();
    dialog?.focus();
  } else if (!dialog.contains(document.activeElement)) {
    event.preventDefault();
    first.focus();
  } else if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

export function useDialogFocus({ open, onClose }) {
  const dialogRef = useRef(null);
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
    initialFocus?.focus();

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
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [open]);

  return {
    dialogRef,
    constrainFocus: (event) => constrainDialogFocus(event, dialogRef.current),
  };
}
