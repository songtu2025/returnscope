import { useEffect, useState } from "react";
import { navigateHash } from "../../app/hashRouter";
import {
  createDashboardSelection,
  selectionItem,
} from "../analysis-dashboards/dashboardSelectionStorage";
import { pendingCount } from "./reviewBatchPresentation";
import { resultRouteQuery } from "./reviewBatchRoute";
import { useReviewBatchData } from "./useReviewBatchData";
import { useReviewRecordEditing } from "./useReviewRecordEditing";
import { useReviewBulkEditing } from "./useReviewBulkEditing";
import { useReviewPublication } from "./useReviewPublication";

/** @param {import("./reviewWorkspaceContracts").ReviewWorkspaceProps} props */
export function useReviewWorkspace({ route, updateRoute, notify, userId }) {
  const {
    batchState,
    recordsState,
    labels,
    recordQuery,
    loadBatch,
    loadRecords,
    setBatchState,
    setRecordsState,
  } = useReviewBatchData({ route, notify });
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
  const readOnly = batch?.status === "published";

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
      resultRouteQuery(route, batch.derived_result_version_id),
    );
  };

  const createDashboardFromDerived = () => {
    if (!batch?.derived_result_version_id) return;
    const token = createDashboardSelection(userId, {
      selected: [
        selectionItem({
          version_id: batch.derived_result_version_id,
          version: batch.derived_version_no,
          result_state: "review-derived",
          quality_status: batch.derived_quality_status || "ready",
          store_site: batch.store_site,
          listing: batch.listing,
          record_count: batch.base_record_count || batch.record_count,
          unit_count: batch.base_unit_count || batch.unit_count,
          published_at: batch.derived_published_at,
        }),
      ],
    });
    navigateHash("analysis-dashboards", { selection_token: token, step: "check" });
  };
  const totalPages = Math.max(
    Math.ceil(Number(records?.total || 0) / route.pageSize),
    1,
  );
  const input = {
    route,
    updateRoute,
    notify,
    userId,
    batchState,
    recordsState,
    labels,
    recordQuery,
    loadBatch,
    loadRecords,
    setBatchState,
    setRecordsState,
    filters,
    setFilters,
    batch,
    records,
    recordItems,
    pending,
    readOnly,
    returnToList,
    openDerivedVersion,
    createDashboardFromDerived,
    totalPages,
  };
  const editing = useReviewRecordEditing(input);
  const bulk = useReviewBulkEditing(input);
  const publication = useReviewPublication(input);
  return {
    route,
    updateRoute,
    notify,
    userId,
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
    readOnly,
    returnToList,
    openDerivedVersion,
    createDashboardFromDerived,
    totalPages,
    ...editing,
    ...bulk,
    ...publication,
  };
}
