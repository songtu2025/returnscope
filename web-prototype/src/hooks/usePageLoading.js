import { createContext, useContext, useId, useLayoutEffect } from "react";

export const PageLoadingContext = createContext(
  /** @type {((id: string, active: boolean) => void) | null} */ (null),
);

/** 页面首读向常驻提示汇报，局部刷新仍在原区域显示。
 * @param {boolean} active
 * @param {boolean} page
 */
export function usePageLoading(active, page) {
  const report = useContext(PageLoadingContext);
  const id = useId();
  const scoped = page && report !== null;
  useLayoutEffect(() => {
    if (!scoped) return undefined;
    report(id, active);
    return () => report(id, false);
  }, [active, id, report, scoped]);
  return scoped;
}
