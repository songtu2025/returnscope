import { useEffect, useRef, useState } from "react";

/** @typedef {import("./analysisDashboardContracts").DashboardRecord} DashboardRecord */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {ReturnType<typeof import("./useReturnReasonEvidence").useReturnReasonEvidence>} EvidenceView */
/** @typedef {{record: DashboardRecord, position: number, scope: string}} Selection */
/** @param {{route: DashboardRoute, reason?: string, evidenceView: EvidenceView, updateRoute: (changes: Partial<DashboardRoute>) => void, onOpenChange?: (open: boolean) => void}} props */
export function useDashboardEvidenceNavigation({
  route,
  reason,
  evidenceView,
  updateRoute,
  onOpenChange,
}) {
  const { evidence, evidencePage, evidenceLoading, evidenceError, onEvidenceRetry } =
    evidenceView;
  const [selection, setSelection] = useState(/** @type {Selection | null} */ (null));
  const [pending, setPending] = useState(/** @type {number | null} */ (null));
  const returnFocusRef = useRef(/** @type {HTMLElement | null} */ (null));
  const pageSize = evidence.page_size || 10;
  const scope = JSON.stringify([
    route.dashboardId,
    route.versionId,
    reason,
    route.subject,
    route.labelGroup,
    route.listing,
    route.productName,
    route.productSku,
    route.dateFrom,
    route.dateTo,
  ]);
  const active = selection?.scope === scope ? selection : null;
  useEffect(() => {
    setSelection(null);
    setPending(null);
    onOpenChange?.(false);
    return () => onOpenChange?.(false);
  }, [scope, onOpenChange]);
  useEffect(() => {
    if (pending === null || !active || evidenceLoading || evidenceError) return;
    if (Math.floor(pending / pageSize) + 1 !== evidencePage) return;
    const record = evidence.items[pending % pageSize];
    setSelection(record ? { record, position: pending, scope } : null);
    setPending(null);
    if (!record) onOpenChange?.(false);
  }, [
    pending,
    active,
    evidenceLoading,
    evidenceError,
    evidencePage,
    evidence.items,
    pageSize,
    scope,
    onOpenChange,
  ]);

  const open = (
    /** @type {DashboardRecord} */ record,
    /** @type {HTMLElement | null} */ trigger,
  ) => {
    const index = evidence.items.findIndex(
      (item) =>
        (item.id || item.source_record_id) === (record.id || record.source_record_id),
    );
    if (index < 0 || evidenceLoading) return;
    returnFocusRef.current = trigger;
    setSelection({ record, position: (evidencePage - 1) * pageSize + index, scope });
    setPending(null);
    onOpenChange?.(true);
  };
  const close = () => {
    // 跨页后原触发按钮已卸载，关闭时返回当前证据所在行。
    const trigger = Array.from(
      document.querySelectorAll("[data-dashboard-evidence-id]"),
    ).find(
      (element) =>
        element.getAttribute("data-dashboard-evidence-id") ===
        (active?.record.id || active?.record.source_record_id),
    );
    if (trigger instanceof HTMLElement) returnFocusRef.current = trigger;
    setSelection(null);
    setPending(null);
    onOpenChange?.(false);
  };
  const move = (/** @type {number} */ direction) => {
    if (!active || pending !== null || evidenceLoading) return;
    const position = active.position + direction;
    if (position < 0 || position >= evidence.total) return;
    const page = Math.floor(position / pageSize) + 1;
    if (page === evidencePage) {
      setSelection({ record: evidence.items[position % pageSize], position, scope });
    } else {
      setPending(position);
      updateRoute({ recordPage: page });
    }
  };
  return {
    record: active?.record || null,
    returnFocusRef,
    open,
    close,
    move,
    position: active?.position || 0,
    total: evidence.total,
    busy: pending !== null && !evidenceError,
    locked: pending !== null,
    error: pending !== null ? evidenceError : "",
    retry: onEvidenceRetry,
  };
}
