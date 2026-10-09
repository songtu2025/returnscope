import { useEffect, useRef, useState } from "react";

const OPEN_EVENT = "seekway-details-open";
const ACTION_SELECTOR = "button:not(:disabled), a[href]";

/** @param {HTMLDetailsElement | null} details @returns {HTMLElement[]} */
function actions(details) {
  return [...(details?.querySelectorAll(ACTION_SELECTOR) ?? [])]
    .filter((element) => element instanceof HTMLElement)
    .filter((element) => !element.closest("[hidden]"));
}

/** @param {import("react").KeyboardEvent<HTMLDetailsElement>} event */
function moveMenuFocus(event) {
  const items = actions(event.currentTarget);
  const current = items.indexOf(/** @type {HTMLElement} */ (document.activeElement));
  const positions = {
    ArrowDown: (current + 1) % items.length,
    ArrowUp:
      current < 0 ? items.length - 1 : (current - 1 + items.length) % items.length,
    Home: 0,
    End: items.length - 1,
  };
  const index = positions[/** @type {keyof typeof positions} */ (event.key)];
  if (index === undefined) return;
  event.preventDefault();
  items[index]?.focus();
}

/** @param {{menu?: boolean, initialFocus?: string, disabled?: boolean}} options */
export function useDismissibleDetails({
  menu = false,
  initialFocus,
  disabled = false,
} = {}) {
  const [open, setOpen] = useState(false);
  const ref = useRef(/** @type {HTMLDetailsElement | null} */ (null));
  const keyboardFocus = useRef("");
  const close = () => {
    setOpen(false);
    ref.current?.querySelector("summary")?.focus();
  };

  useEffect(() => {
    if (!open) return undefined;
    const details = ref.current;
    document.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail: details }));
    const focusSelector = initialFocus || (keyboardFocus.current && ACTION_SELECTOR);
    const items = actions(details);
    const focusTarget =
      keyboardFocus.current === "last"
        ? items.at(-1)
        : focusSelector && details?.querySelector(focusSelector);
    if (focusTarget instanceof HTMLElement) focusTarget.focus();
    keyboardFocus.current = "";
    /** @param {PointerEvent} event */
    const outside = (event) => {
      if (event.target instanceof Node && !details?.contains(event.target))
        setOpen(false);
    };
    /** @param {Event} event */
    const anotherOpened = (event) => {
      if (event instanceof CustomEvent && event.detail !== details) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener(OPEN_EVENT, anotherOpened);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener(OPEN_EVENT, anotherOpened);
    };
  }, [open, initialFocus]);

  /** @param {import("react").KeyboardEvent<HTMLDetailsElement>} event */
  const onKeyDown = (event) => {
    if (open && event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close();
    } else if (menu && !disabled && ["ArrowDown", "ArrowUp"].includes(event.key)) {
      if (open) moveMenuFocus(event);
      else {
        event.preventDefault();
        keyboardFocus.current = event.key === "ArrowUp" ? "last" : "first";
        setOpen(true);
      }
    } else if (menu && open) moveMenuFocus(event);
  };

  return {
    close,
    detailsProps: {
      ref,
      open,
      onKeyDown,
      onBlur: (/** @type {import("react").FocusEvent<HTMLDetailsElement>} */ event) => {
        if (!open || event.currentTarget.contains(event.relatedTarget)) return;
        // 按钮因请求或数值上限禁用时，浏览器会把焦点移到页面，不应关闭设置。
        if (
          !event.relatedTarget &&
          event.target instanceof HTMLElement &&
          event.target.matches(":disabled")
        ) {
          ref.current?.querySelector("summary")?.focus();
          return;
        }
        setOpen(false);
      },
      onClickCapture: (
        /** @type {import("react").MouseEvent<HTMLDetailsElement>} */ event,
      ) => {
        if (!open || !(event.target instanceof Element)) return;
        const action = event.target.closest(ACTION_SELECTOR);
        if (action && (menu || action.hasAttribute("data-close-details"))) close();
      },
    },
    summaryProps: {
      "aria-expanded": open,
      "aria-disabled": disabled || undefined,
      onKeyDown: (/** @type {import("react").KeyboardEvent<HTMLElement>} */ event) => {
        if (!["Enter", " "].includes(event.key)) return;
        event.preventDefault();
        if (!disabled) event.currentTarget.click();
      },
      onClick: (/** @type {import("react").MouseEvent<HTMLElement>} */ event) => {
        event.preventDefault();
        if (disabled) return;
        keyboardFocus.current = menu && event.detail === 0 ? "first" : "";
        setOpen((current) => !current);
      },
    },
  };
}
