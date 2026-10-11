import { useEffect, useState } from "react";
import { navigateHash } from "../../app/hashRouter";
import { pendingCount } from "./reviewBatchPresentation";
import { resultRouteQuery } from "./reviewBatchRoute";
import { useReviewBatchData } from "./useReviewBatchData";

/** @param {import("./reviewWorkspaceContracts").ReviewWorkspaceProps} props */
export function useReviewWorkspace({ route, updateRoute, notify }) {
  const { batchState, recordsState, labels, loadBatch, loadRecords } =
    useReviewBatchData({ route, notify });
  const [selected, setSelected] = useState(
    /** @type {import("../../shared/api/reviewBatchContracts").ReviewRecord | null} */ (
      null
    ),
  );
  const [filters, setFilters] = useState({
    q: route.q,
    status: route.status,
    listing: route.listing,
    productName: route.productName,
    productSku: route.productSku,
    orderId: route.orderId,
  });

  useEffect(() => {
    setFilters({
      q: route.q,
      status: route.status,
      listing: route.listing,
      productName: route.productName,
      productSku: route.productSku,
      orderId: route.orderId,
    });
  }, [
    route.listing,
    route.orderId,
    route.productName,
    route.productSku,
    route.q,
    route.status,
  ]);

  const batch = batchState.data?.id === route.batchId ? batchState.data : null;
  const records = recordsState.batchId === route.batchId ? recordsState.data : null;
  const recordItems = records?.items ?? [];
  const pending = pendingCount(batch);
  useEffect(() => setSelected(null), [route.batchId]);

  const returnToList = () =>
    updateRoute({
      batchId: "",
      status: "",
      page: 1,
      listing: "",
      productName: "",
      productSku: "",
      orderId: "",
      q: "",
    });

  const openDerivedVersion = () => {
    if (!batch?.derived_result_version_id) return;
    navigateHash(
      "classification-results",
      resultRouteQuery(route, batch.derived_result_version_id, "history"),
    );
  };

  const totalPages = Math.max(
    Math.ceil(Number(records?.total || 0) / route.pageSize),
    1,
  );
  return {
    route,
    updateRoute,
    notify,
    batchState,
    recordsState,
    labels,
    loadBatch,
    loadRecords,
    filters,
    setFilters,
    batch,
    records,
    recordItems,
    pending,
    readOnly: true,
    returnToList,
    openDerivedVersion,
    totalPages,
    selected,
    setSelected,
    openRecord: setSelected,
  };
}
