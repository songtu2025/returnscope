import { useProtectedData } from "../../hooks/useProtectedData";
import { useDataRefresh } from "../../hooks/useDataRefresh";
import { MANAGED_REFRESH_OPTIONS } from "../../shared/refreshPolicy";
import { useLayoutEffect, useRef, useState } from "react";
import useSWR from "swr";
import { ProductDimensionToolbar } from "./ProductDimensionToolbar";
import { api } from "../../api";
import { ProductLoadFeedback } from "./ProductLoadFeedback";

import { ProductDimensionEditDialog } from "./ProductDimensionEditDialog";
import { ProductDimensionTable } from "./ProductDimensionTable";

/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRecord} DatasetRecord */
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRowsPage} DatasetRowsPage */
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRow} DatasetRow */
/** @typedef {Error & {status?: number}} DataRequestError */

/** @param {unknown} error @returns {DataRequestError} */
function requestError(error) {
  return error instanceof Error
    ? /** @type {DataRequestError} */ (error)
    : new Error("请求失败");
}

/** @param {{dataset: DatasetRecord, notify: (message: string, tone?: string) => void, onChanged: (dataset: DatasetRecord) => void, onEditingChange?: (editing: boolean) => void, onRefresh?: () => Promise<unknown>, parentError?: boolean}} props */
export function ProductDimensionRows({
  dataset,
  notify,
  onChanged,
  onEditingChange,
  onRefresh,
  parentError = false,
}) {
  const [editing, setEditing] = useState(/** @type {DatasetRow | null} */ (null));
  const editingVersion = useRef(dataset.current_version);
  const [conflict, setConflict] = useState(false);
  const isEditing = Boolean(editing);
  useLayoutEffect(() => {
    onEditingChange?.(isEditing);
    return () => onEditingChange?.(false);
  }, [isEditing, onEditingChange]);
  const [query, setQuery] = useState("");
  const [draftQuery, setDraftQuery] = useState("");
  const [store, setStore] = useState("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const [saving, setSaving] = useState(false);
  const [changeNote, setChangeNote] = useState("");
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
  /** @param {import("react").FormEvent<HTMLFormElement>} event */
  const save = async (event) => {
    event.preventDefault();
    if (!editing || conflict) return;
    setSaving(true);
    try {
      const updated = await api.updateDatasetRow(dataset.id, {
        row_index: editing._row_index,
        expected_version: editingVersion.current,
        changes: {
          MSKU: editing.MSKU,
          "店铺/站点": editing["店铺/站点"],
          Listing: editing.Listing,
          ...(editing["产品名称"] !== undefined
            ? { 产品名称: editing["产品名称"] }
            : {}),
          ...(editing["品类A"] !== undefined ? { 品类A: editing["品类A"] } : {}),
          ...(editing["品类B"] !== undefined ? { 品类B: editing["品类B"] } : {}),
        },
        change_note: changeNote,
      });
      setEditing(null);
      onChanged(updated);
      notify("产品信息已更新");
    } catch (error) {
      const nextError = requestError(error);
      if (nextError.status === 409) {
        setConflict(true);
        await api
          .dataset(dataset.id, { include: "" })
          .then(onChanged)
          .catch(() => notify("资料同步失败，输入已保留，可关闭后刷新", "error"));
        notify("数据已更新，输入已保留，请核对最新资料后重新修改", "error");
      } else notify(nextError.message, "error");
    } finally {
      setSaving(false);
    }
  };
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
          onEdit={(row) => {
            editingVersion.current = dataset.current_version;
            setConflict(false);
            setEditing(row);
            setChangeNote("");
          }}
        />
      )}
      {editing && (
        <ProductDimensionEditDialog
          editing={editing}
          setEditing={setEditing}
          changeNote={changeNote}
          setChangeNote={setChangeNote}
          saving={saving}
          conflict={conflict}
          onSave={save}
          onClose={() => setEditing(null)}
        />
      )}
    </section>
  );
}
