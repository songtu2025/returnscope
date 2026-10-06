import { useCallback, useEffect, useState } from "react";
import { ArrowClockwise, MagnifyingGlass } from "@phosphor-icons/react";
import Button from "antd/es/button";
import Input from "antd/es/input";
import { api } from "../../api";
import { InlineLoading } from "../../components/SharedUi";

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

/** @param {{dataset: DatasetRecord, notify: (message: string, tone?: string) => void, onChanged: (dataset: DatasetRecord) => void}} props */
export function ProductDimensionRows({ dataset, notify, onChanged }) {
  const [data, setData] = useState(/** @type {DatasetRowsPage | null} */ (null));
  const [editing, setEditing] = useState(/** @type {DatasetRow | null} */ (null));
  const [query, setQuery] = useState("");
  const [draftQuery, setDraftQuery] = useState("");
  const [store, setStore] = useState("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const [saving, setSaving] = useState(false);
  const [changeNote, setChangeNote] = useState("");
  const pageSize = 15;
  const load = useCallback(
    () =>
      api
        .datasetRows(dataset.id, query, (page - 1) * pageSize, pageSize, {
          store,
          category,
        })
        .then(setData),
    [category, dataset.id, page, query, store],
  );
  useEffect(() => {
    load().catch((error) => notify(error.message, "error"));
  }, [load, notify, dataset.current_version]);
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / pageSize));
  const pageStart = Math.min(Math.max(1, page - 2), Math.max(1, totalPages - 4));
  const visiblePages = Array.from(
    { length: Math.min(5, totalPages) },
    (_, index) => pageStart + index,
  );
  /** @param {import("react").FormEvent<HTMLFormElement>} event */
  const save = async (event) => {
    event.preventDefault();
    if (!editing) return;
    setSaving(true);
    try {
      const updated = await api.updateDatasetRow(dataset.id, {
        row_index: editing._row_index,
        expected_version: dataset.current_version,
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
      notify("产品信息已更新，并创建了新版本");
    } catch (error) {
      const nextError = requestError(error);
      if (nextError.status === 409) {
        setEditing(null);
        onChanged(await api.dataset(dataset.id, { include: "versions" }));
        notify("数据已被其他用户更新，已刷新到最新版本，请重新修改", "error");
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
        notify={notify}
      />
      {!data && <InlineLoading label="读取产品信息…" />}
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
            setEditing(row);
            setChangeNote("");
          }}
        />
      )}
      {editing && (
        <ProductDimensionEditDialog
          dataset={dataset}
          editing={editing}
          setEditing={setEditing}
          changeNote={changeNote}
          setChangeNote={setChangeNote}
          saving={saving}
          onSave={save}
          onClose={() => setEditing(null)}
        />
      )}
    </section>
  );
}

/** @param {{draftQuery: string, setDraftQuery: (value: string) => void, setPage: (value: number) => void, setQuery: (value: string) => void}} props */
function ProductDimensionSearch({ draftQuery, setDraftQuery, setPage, setQuery }) {
  return (
    <form
      className="dimension-search"
      onSubmit={(event) => {
        event.preventDefault();
        setPage(1);
        setQuery(draftQuery);
      }}
    >
      <Input
        aria-label="搜索产品信息"
        prefix={<MagnifyingGlass size={15} />}
        value={draftQuery}
        onChange={(event) => setDraftQuery(event.target.value)}
        placeholder="搜索 MSKU、商品名称或 Listing"
      />
      <Button htmlType="submit" autoInsertSpace={false}>
        搜索
      </Button>
    </form>
  );
}

/** @param {{data: DatasetRowsPage | null, store: string, category: string, setStore: (value: string) => void, setCategory: (value: string) => void, setPage: (value: number) => void}} props */
function ProductDimensionFilters({
  data,
  store,
  category,
  setStore,
  setCategory,
  setPage,
}) {
  return (
    <div className="product-master-filters">
      <label>
        店铺/站点
        <select
          value={store}
          onChange={(event) => {
            setPage(1);
            setStore(event.target.value);
          }}
        >
          <option value="">全部</option>
          {(data?.facets?.stores ?? []).map((value) => (
            <option value={value} key={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <label>
        品类
        <select
          value={category}
          onChange={(event) => {
            setPage(1);
            setCategory(event.target.value);
          }}
        >
          <option value="">全部</option>
          {(data?.facets?.categories ?? []).map((value) => (
            <option value={value} key={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

/** @param {{data: DatasetRowsPage | null, dataset: DatasetRecord, draftQuery: string, setDraftQuery: (value: string) => void, setPage: (value: number) => void, setQuery: (value: string) => void, store: string, setStore: (value: string) => void, category: string, setCategory: (value: string) => void, load: () => Promise<void>, notify: (message: string, tone?: string) => void}} props */
function ProductDimensionToolbar({
  data,
  dataset,
  draftQuery,
  setDraftQuery,
  setPage,
  setQuery,
  store,
  setStore,
  category,
  setCategory,
  load,
  notify,
}) {
  return (
    <div className="dimension-table-toolbar">
      <ProductDimensionSearch
        draftQuery={draftQuery}
        setDraftQuery={setDraftQuery}
        setPage={setPage}
        setQuery={setQuery}
      />
      <ProductDimensionFilters
        data={data}
        store={store}
        category={category}
        setStore={setStore}
        setCategory={setCategory}
        setPage={setPage}
      />
      <div>
        <span>共 {(data?.total ?? dataset.row_count).toLocaleString()} 条产品</span>
        <Button
          autoInsertSpace={false}
          icon={<ArrowClockwise size={15} />}
          onClick={() => load().catch((error) => notify(error.message, "error"))}
        >
          刷新
        </Button>
      </div>
    </div>
  );
}
