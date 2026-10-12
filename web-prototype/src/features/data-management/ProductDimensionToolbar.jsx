import { ArrowClockwise, MagnifyingGlass } from "@phosphor-icons/react";
import Button from "antd/es/button";
import Input from "antd/es/input";
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRecord} DatasetRecord */
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRowsPage} DatasetRowsPage */

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
        placeholder="搜索 MSKU、产品名称或 Listing"
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

/** @param {{data: DatasetRowsPage | null, dataset: DatasetRecord, draftQuery: string, setDraftQuery: (value: string) => void, setPage: (value: number) => void, setQuery: (value: string) => void, store: string, setStore: (value: string) => void, category: string, setCategory: (value: string) => void, load: () => Promise<unknown>, loading: boolean}} props */
export function ProductDimensionToolbar({
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
  loading,
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
          disabled={loading}
          onClick={() => load()}
        >
          刷新
        </Button>
      </div>
    </div>
  );
}
