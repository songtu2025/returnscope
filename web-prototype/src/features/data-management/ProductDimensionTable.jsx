import { CheckCircle } from "@phosphor-icons/react";

import { Pagination } from "../../components/Pagination";
import { PRODUCT_PAGE_SIZES } from "../../shared/pagination";
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRowsPage} DatasetRowsPage */
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRow} DatasetRow */
/** @typedef {import("react").Dispatch<import("react").SetStateAction<number>>} SetPage */

/** @param {{row: DatasetRow, onEdit: (row: DatasetRow) => void}} props */
function ProductDimensionRow({ row, onEdit }) {
  return (
    <div key={row._row_index}>
      <code title={row.MSKU}>{row.MSKU || "—"}</code>
      <span title={row["店铺/站点"]}>{row["店铺/站点"] || "—"}</span>
      <span title={row.Listing}>{row.Listing || "—"}</span>
      <span title={row["产品名称"]}>{row["产品名称"] || "—"}</span>
      <span title={[row["品类A"], row["品类B"]].filter(Boolean).join(" > ")}>
        {[row["品类A"], row["品类B"]].filter(Boolean).join(" > ") || "待补充"}
      </span>
      <span className="product-master-status">
        <CheckCircle size={14} weight="fill" />
        生效
      </span>
      <button
        type="button"
        aria-label={`编辑 ${row.MSKU} 产品信息`}
        onClick={() => onEdit(row)}
      >
        编辑信息
      </button>
    </div>
  );
}

/** @param {{hasFilters: boolean, clearFilters: () => void}} props */
function ProductRowsEmpty({ hasFilters, clearFilters }) {
  return (
    <div className="dimension-empty">
      <span>没有匹配的产品信息。</span>
      {hasFilters && (
        <button type="button" onClick={clearFilters}>
          清除筛选
        </button>
      )}
    </div>
  );
}

/** @param {{data: DatasetRowsPage, hasFilters: boolean, clearFilters: () => void, onEdit: (row: DatasetRow) => void}} props */
function ProductRowsTable({ data, hasFilters, clearFilters, onEdit }) {
  return (
    <div className="dimension-table">
      <div className="table-head">
        <span>MSKU</span>
        <span>店铺 / 站点</span>
        <span>Listing</span>
        <span>产品名称</span>
        <span>品类</span>
        <span>状态</span>
        <span>操作</span>
      </div>
      {data.records.map((row) => (
        <ProductDimensionRow key={row._row_index} row={row} onEdit={onEdit} />
      ))}
      {data.records.length === 0 && (
        <ProductRowsEmpty hasFilters={hasFilters} clearFilters={clearFilters} />
      )}
    </div>
  );
}

/** @param {{data: DatasetRowsPage, hasFilters: boolean, clearFilters: () => void, onEdit: (row: DatasetRow) => void, pageSize: number, page: number, totalPages: number, setPage: SetPage, setPageSize: (pageSize: number) => void}} props */
export function ProductDimensionTable({
  data,
  hasFilters,
  clearFilters,
  onEdit,
  page,
  pageSize,
  totalPages,
  setPage,
  setPageSize,
}) {
  return (
    <>
      <ProductRowsTable
        data={data}
        hasFilters={hasFilters}
        clearFilters={clearFilters}
        onEdit={onEdit}
      />
      <Pagination
        page={page}
        pageSize={pageSize}
        total={data.total}
        totalPages={totalPages}
        onPage={setPage}
        onPageSize={setPageSize}
        pageSizeOptions={PRODUCT_PAGE_SIZES}
        showQuickJumper
      />
    </>
  );
}
