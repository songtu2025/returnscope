import { useContext, useEffect, useRef } from "react";
import { PageLoadingContext } from "./usePageLoading";

/** @typedef {{identity: string, id: string, top: number, left: number}} ListReturnPosition */
/**
 * @param {{identity: string, active?: boolean, ready: boolean,
 * snapshotRef?: import("react").MutableRefObject<ListReturnPosition | null>}} options
 */
export function useListReturnPosition({ identity, active = true, ready, snapshotRef }) {
  const positionRef = useRef(
    snapshotRef ?? { current: /** @type {ListReturnPosition | null} */ (null) },
  );
  const containerRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const titleRef = useRef(/** @type {HTMLHeadingElement | null} */ (null));
  const restored = useRef({ identity, done: false });
  const loading = useContext(PageLoadingContext);
  useEffect(() => {
    if (!active || restored.current.identity !== identity) {
      restored.current = { identity, done: false };
    }
    if (!active || !ready || loading?.initial || restored.current.done) return;
    restored.current.done = true;
    const saved = positionRef.current.current;
    positionRef.current.current = null;
    if (!saved || saved.identity !== identity) {
      if (window.scrollY || window.scrollX) {
        window.scrollTo({ top: 0, left: 0, behavior: "auto" });
      }
      return;
    }
    const target = [
      ...(containerRef.current?.querySelectorAll("[data-list-return-id]") ?? []),
    ].find((element) => element.getAttribute("data-list-return-id") === saved.id);
    if (target instanceof HTMLElement) {
      window.scrollTo({ top: saved.top, left: saved.left, behavior: "auto" });
      target.focus({ preventScroll: true });
    } else {
      window.scrollTo({ top: 0, left: 0, behavior: "auto" });
      titleRef.current?.focus({ preventScroll: true });
    }
  }, [active, identity, loading?.initial, ready, positionRef]);
  return {
    containerRef,
    titleRef,
    remember: (/** @type {string} */ id) => {
      positionRef.current.current = {
        identity,
        id,
        top: window.scrollY,
        left: window.scrollX,
      };
    },
  };
}
