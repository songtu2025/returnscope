import { createContext, useContext, useId, useLayoutEffect } from "react";

export const PageLoadingContext = createContext(
  /** @type {{report: (id: string, active: boolean) => void, initial: boolean} | null} */ (
    null
  ),
);

/** 首次进入合并必要读取；页面展示后，后续加载留在原区域。
 * @param {boolean} active
 * @param {boolean} page
 */
export function usePageLoading(active, page) {
  const context = useContext(PageLoadingContext);
  const report = context?.report;
  const id = useId();
  const scoped = page && Boolean(context?.initial);
  useLayoutEffect(() => {
    if (!scoped || !report) return undefined;
    report(id, active);
    return () => report(id, false);
  }, [active, id, report, scoped]);
  return scoped;
}
