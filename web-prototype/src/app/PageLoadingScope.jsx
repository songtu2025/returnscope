import { useCallback, useEffect, useRef, useState } from "react";
import { InlineLoading } from "../components/SharedUi";
import { PageLoadingContext } from "../hooks/usePageLoading";

/** @param {{children: import("react").ReactNode}} props */
export function PageLoadingScope({ children }) {
  const [pending, setPending] = useState(/** @type {Set<string>} */ (new Set()));
  const [visible, setVisible] = useState(false);
  const startedAt = useRef(/** @type {number | null} */ (null));
  const report = useCallback(
    /** @param {string} id @param {boolean} active */ (id, active) => {
      setPending((current) => {
        if (current.has(id) === active) return current;
        const next = new Set(current);
        if (active) next.add(id);
        else next.delete(id);
        return next;
      });
    },
    [],
  );
  const busy = pending.size > 0;
  useEffect(() => {
    let timer;
    if (busy) {
      if (startedAt.current === null) startedAt.current = performance.now();
      timer = window.setTimeout(
        () => setVisible(true),
        Math.max(0, 200 - (performance.now() - startedAt.current)),
      );
    } else {
      // 留给下一次提交交接加载阶段；空闲期间不触发首次显示。
      timer = window.setTimeout(() => {
        startedAt.current = null;
        setVisible(false);
      }, 80);
    }
    return () => window.clearTimeout(timer);
  }, [busy]);
  return (
    <PageLoadingContext value={report}>
      <div className="page-loading-scope" aria-busy={busy}>
        <div className="page-loading-slot">
          <InlineLoading label="正在读取页面…" active={visible} delay={0} />
        </div>
        {children}
      </div>
    </PageLoadingContext>
  );
}
