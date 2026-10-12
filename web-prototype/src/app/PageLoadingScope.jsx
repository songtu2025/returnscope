import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { InlineLoading, PageHeading } from "../components/SharedUi";
import { PageLoadingContext } from "../hooks/usePageLoading";

/** @param {{children: import("react").ReactNode, title?: string}} props */
export function PageLoadingScope({ children, title }) {
  const [pending, setPending] = useState(/** @type {Set<string>} */ (new Set()));
  const [visible, setVisible] = useState(false);
  const [initial, setInitial] = useState(true);
  const [holding, setHolding] = useState(false);
  const startedAt = useRef(/** @type {number | null} */ (null));
  const report = useCallback(
    /** @param {string} id @param {boolean} active */ (id, active) => {
      if (active) {
        if (startedAt.current === null) startedAt.current = performance.now();
        setHolding(true);
      }
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
    if (!initial) return undefined;
    // 已有缓存且没有首读请求时立即结束首读，随后操作不会隐藏已展示的正文。
    if (!busy && startedAt.current === null) {
      setInitial(false);
      return undefined;
    }
    let timer;
    if (busy) {
      timer = window.setTimeout(
        () => setVisible(true),
        Math.max(
          0,
          200 - (performance.now() - (startedAt.current ?? performance.now())),
        ),
      );
    } else {
      // 留给下一次提交交接加载阶段；空闲期间不触发首次显示。
      timer = window.setTimeout(() => {
        startedAt.current = null;
        setVisible(false);
        setInitial(false);
        setHolding(false);
      }, 80);
    }
    return () => window.clearTimeout(timer);
  }, [busy, initial]);
  const blocking = initial && (busy || holding);
  const context = useMemo(() => ({ report, initial }), [report, initial]);
  return (
    <PageLoadingContext value={context}>
      <div
        className={`page-loading-scope${blocking ? " is-initial-loading" : ""}`}
        aria-busy={blocking}
      >
        {blocking && title && (
          <div className="standard-page page-loading-heading">
            <PageHeading title={title} />
          </div>
        )}
        <div className="page-loading-slot">
          <InlineLoading label="正在读取页面…" active={visible} delay={0} />
        </div>
        {/* 保持挂载以继续读取依赖数据，首读结束前只展示页头和返回入口。 */}
        <div
          className="page-loading-content"
          style={{ visibility: blocking ? "hidden" : undefined }}
        >
          {children}
        </div>
      </div>
    </PageLoadingContext>
  );
}
