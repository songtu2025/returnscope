import { useEffect, useState } from "react";
import { dashboardApi } from "../../shared/api/dashboardApi";

/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").InsightReason} InsightReason */
/** @typedef {import("./analysisDashboardContracts").InsightEvidence} InsightEvidence */
/** @typedef {{key: string, data: InsightEvidence | null, loading: boolean, error: string}} EvidencePageState */
/** @typedef {Pick<DashboardRoute, "dashboardId" | "versionId" | "subject" | "labelGroup" | "listing" | "productName" | "productSku" | "dateFrom" | "dateTo">} EvidenceRequestRoute */
/** @typedef {{route: EvidenceRequestRoute, selected?: {value?: string}, evidenceReady: boolean, evidencePageNumber: number, evidenceKey: string, setEvidencePage: import("react").Dispatch<import("react").SetStateAction<EvidencePageState>>}} EvidencePageRequest */

/** @param {DashboardRoute} route @param {InsightReason | undefined} selected @param {number} evidencePageNumber @param {number} evidenceRetry */
function evidencePageKey(route, selected, evidencePageNumber, evidenceRetry) {
  const evidenceKey = JSON.stringify([
    route.dashboardId,
    route.versionId,
    selected?.value,
    route.subject,
    route.labelGroup,
    route.listing,
    route.productName,
    route.productSku,
    route.dateFrom,
    route.dateTo,
    evidencePageNumber,
    evidenceRetry,
  ]);
  return evidenceKey;
}

/** @param {EvidencePageRequest} request */
function requestEvidencePage({
  route,
  selected,
  evidenceReady,
  evidencePageNumber,
  evidenceKey,
  setEvidencePage,
}) {
  if (!evidenceReady || evidencePageNumber === 1 || !selected?.value) return;
  const controller = new AbortController();
  setEvidencePage({ key: evidenceKey, data: null, loading: true, error: "" });
  dashboardApi
    .analysisDashboardEvidence(
      route.dashboardId,
      route.versionId,
      {
        problem: selected.value,
        subject: route.subject,
        label_group: route.labelGroup,
        listing: route.listing,
        product_name: route.productName,
        product_sku: route.productSku,
        date_from: route.dateFrom,
        date_to: route.dateTo,
        page: evidencePageNumber,
      },
      { signal: controller.signal },
    )
    .then((response) => {
      if (!controller.signal.aborted) {
        setEvidencePage({
          key: evidenceKey,
          data: response,
          loading: false,
          error: "",
        });
      }
    })
    .catch((requestError) => {
      if (!controller.signal.aborted) {
        setEvidencePage({
          key: evidenceKey,
          data: null,
          loading: false,
          error:
            requestError instanceof Error ? requestError.message : String(requestError),
        });
      }
    });
  return () => controller.abort();
}

/** @param {EvidencePageState} evidencePage @param {string} evidenceKey @param {number} evidencePageNumber @param {InsightEvidence} evidence */
function evidencePagePresentation(
  evidencePage,
  evidenceKey,
  evidencePageNumber,
  evidence,
) {
  const currentEvidencePage = evidencePage.key === evidenceKey ? evidencePage : null;
  const visibleEvidence =
    evidencePageNumber === 1
      ? evidence
      : (currentEvidencePage?.data ?? { items: [], total: evidence.total });
  const evidenceLoading =
    evidencePageNumber > 1 && (!currentEvidencePage || currentEvidencePage.loading);

  return {
    evidence: visibleEvidence,
    evidenceLoading,
    evidenceError: currentEvidencePage?.error || "",
  };
}

/** @param {{route: DashboardRoute, selected?: InsightReason, evidenceReady: boolean, evidence: InsightEvidence}} props */
export function useReturnReasonEvidence({ route, selected, evidenceReady, evidence }) {
  const evidencePageNumber = route.recordPage || 1;
  const [evidencePage, setEvidencePage] = useState(
    /** @returns {{key: string, data: import("./analysisDashboardContracts").InsightEvidence | null, loading: boolean, error: string}} */
    () => ({ key: "", data: null, loading: false, error: "" }),
  );
  const [evidenceRetry, setEvidenceRetry] = useState(0);

  const evidenceKey = evidencePageKey(
    route,
    selected,
    evidencePageNumber,
    evidenceRetry,
  );
  useEffect(
    () =>
      requestEvidencePage({
        route: {
          dashboardId: route.dashboardId,
          versionId: route.versionId,
          subject: route.subject,
          labelGroup: route.labelGroup,
          listing: route.listing,
          productName: route.productName,
          productSku: route.productSku,
          dateFrom: route.dateFrom,
          dateTo: route.dateTo,
        },
        selected: { value: selected?.value },
        evidenceReady,
        evidencePageNumber,
        evidenceKey,
        setEvidencePage,
      }),
    [
      evidenceReady,
      evidenceKey,
      evidencePageNumber,
      route.dashboardId,
      route.versionId,
      route.subject,
      route.labelGroup,
      route.listing,
      route.productName,
      route.productSku,
      route.dateFrom,
      route.dateTo,
      selected?.value,
    ],
  );
  return {
    ...evidencePagePresentation(
      evidencePage,
      evidenceKey,
      evidencePageNumber,
      evidence,
    ),
    evidencePage: evidencePageNumber,
    onEvidenceRetry: () => setEvidenceRetry((value) => value + 1),
  };
}
