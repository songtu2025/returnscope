import { useProtectedData } from "../../hooks/useProtectedData";
import { useLoadingHeight } from "../../hooks/useLoadingHeight";
import { useDataRefresh } from "../../hooks/useDataRefresh";
import { MANAGED_REFRESH_OPTIONS } from "../../shared/refreshPolicy";
import { useLayoutEffect, useRef } from "react";
import useSWR from "swr";
import { ProductDimensionToolbar } from "./ProductDimensionToolbar";
import { api } from "../../api";
import { ProductLoadFeedback } from "./ProductLoadFeedback";

import { ProductDimensionEditDialog } from "./ProductDimensionEditDialog";
import { ProductDimensionTable } from "./ProductDimensionTable";
import { useProductRowEditing } from "./useProductRowEditing";
import { useProductListState } from "./useProductListState";

/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRecord} DatasetRecord */
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRowsPage} DatasetRowsPage */
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRow} DatasetRow */
/** @param {{dataset: DatasetRecord, notify: (message: string, tone?: string) => void, onChanged: (dataset: DatasetRecord) => void, onEditingChange?: (editing: boolean) => void, onRefresh?: () => Promise<unknown>, parentError?: boolean}} props */
export function ProductDimensionRows({
  dataset,
  notify,
  onChanged,
  onEditingChange,
  onRefresh,
  parentError = false,
}) {
  const editor = useProductRowEditing({ dataset, notify, onChanged });
  const { editing } = editor;
  const regionRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const isEditing = Boolean(editing);
  useLayoutEffect(() => {
    onEditingChange?.(isEditing);
    return () => onEditingChange?.(false);
  }, [isEditing, onEditingChange]);
  const {
    query,
    draftQuery,
    store,
    category,
    page,
    setDraftQuery,
    setQuery,
    setStore,
    setCategory,
    setPage,
  } = useProductListState();
  const pageSize = 15;
  const {
    data: fetchedData = null,
    error,
    isLoading,
    isValidating,
    mutate,
  } = useSWR(
    [
      "data-assets",
      "products",
      "rows",
      dataset.id,
      dataset.current_version,
      { query, page, store, category },
    ],
    () =>
      api.datasetRows(dataset.id, query, (page - 1) * pageSize, pageSize, {
        store,
        category,
      }),
    MANAGED_REFRESH_OPTIONS,
  );
  const identity = JSON.stringify([
    dataset.id,
    dataset.current_version,
    query,
    page,
    store,
    category,
  ]);
  const data = useProtectedData(fetchedData, Boolean(editing), identity);
  useLoadingHeight(isLoading || isValidating, regionRef);
  useDataRefresh(() => mutate(), { loading: isLoading || isValidating, identity });
  const load = () =>
    onRefresh
      ? onRefresh()
      : mutate((current) => current, { revalidate: true, throwOnError: false });
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / pageSize));
  const pageStart = Math.min(Math.max(1, page - 2), Math.max(1, totalPages - 4));
  const visiblePages = Array.from(
    { length: Math.min(5, totalPages) },
    (_, index) => pageStart + index,
  );
  const clearFilters = () => {
    setDraftQuery("");
    setQuery("");
    setStore("");
    setCategory("");
    setPage(1);
  };
  const hasFilters = Boolean(query || store || category);
  return (
    <section className="dimension-table-panel">
      <ProductDimensionToolbar
        data={data}
        dataset={dataset}
        draftQuery={draftQuery}
        setDraftQuery={setDraftQuery}
        setPage={setPage}
        setQuery={setQuery}
        store={store}
        setStore={setStore}
        category={category}
        setCategory={setCategory}
        load={load}
        loading={isValidating}
      />
      <div
        ref={regionRef}
        className="loading-region"
        aria-busy={isLoading || isValidating}
      >
        <ProductLoadFeedback
          error={parentError ? null : error}
          loading={isLoading || isValidating}
          hasData={Boolean(data)}
          onRetry={load}
        />
        {data && (
          <ProductDimensionTable
            data={data}
            page={page}
            pageSize={pageSize}
            pageStart={pageStart}
            totalPages={totalPages}
            visiblePages={visiblePages}
            setPage={setPage}
            hasFilters={hasFilters}
            clearFilters={clearFilters}
            onEdit={editor.open}
          />
        )}
      </div>
      {editing && (
        <ProductDimensionEditDialog
          {...editor}
          editing={editing}
          onSave={editor.save}
          onClose={editor.close}
        />
      )}
    </section>
  );
}
