import { useLayoutEffect, useRef } from "react";

/** 保留已展示内容的高度，查询期间只更换内容，不推移后续区域。
 * @param {boolean} loading
 * @param {import("react").RefObject<HTMLElement | null>} regionRef
 */
export function useLoadingHeight(loading, regionRef) {
  const heightRef = useRef(0);
  useLayoutEffect(() => {
    const region = regionRef.current;
    if (!region) return undefined;
    if (loading) {
      region.style.minHeight = `${heightRef.current || 112}px`;
      return undefined;
    }
    region.style.minHeight = "";
    const measure = () => {
      heightRef.current = region.getBoundingClientRect().height;
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(region);
    return () => observer.disconnect();
  }, [loading, regionRef]);
}
