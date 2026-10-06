import { CaretLeft, CaretRight, CheckCircle } from "@phosphor-icons/react";

/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRecord} DatasetRecord */
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRowsPage} DatasetRowsPage */
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRow} DatasetRow */
/** @typedef {import("react").Dispatch<import("react").SetStateAction<DatasetRow | null>>} SetEditing */
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

/** @param {{page: number, pageStart: number, totalPages: number, visiblePages: number[], setPage: SetPage}} props */
function ProductPageLinks({ page, pageStart, totalPages, visiblePages, setPage }) {
  return (
    <>
      {pageStart > 1 && (
        <>
          <button type="button" onClick={() => setPage(1)}>
            1
          </button>
          <span>…</span>
        </>
      )}
      {visiblePages.map((value) => (
        <button
          type="button"
          className={value === page ? "active" : ""}
          key={value}
          onClick={() => setPage(value)}
        >
          {value}
        </button>
      ))}
      {(visiblePages.at(-1) ?? 0) < totalPages && (
        <>
          <span>…</span>
          <button type="button" onClick={() => setPage(totalPages)}>
            {totalPages}
          </button>
        </>
      )}
    </>
  );
}

/** @param {{pageSize: number, page: number, pageStart: number, totalPages: number, visiblePages: number[], setPage: SetPage}} props */
function ProductPagination({
  page,
  pageSize,
  pageStart,
  totalPages,
  visiblePages,
  setPage,
}) {
  return (
    <footer className="dimension-pagination">
      <span className="dimension-page-size">{pageSize} 条/页</span>
      <div>
        <button
          type="button"
          aria-label="上一页"
          disabled={page === 1}
          onClick={() => setPage((current) => current - 1)}
        >
          <CaretLeft size={15} />
        </button>
        <ProductPageLinks
          page={page}
          pageStart={pageStart}
          totalPages={totalPages}
          visiblePages={visiblePages}
          setPage={setPage}
        />
        <button
          type="button"
          aria-label="下一页"
          disabled={page === totalPages}
          onClick={() => setPage((current) => current + 1)}
        >
          <CaretRight size={15} />
        </button>
      </div>
    </footer>
  );
}

/** @param {{data: DatasetRowsPage, hasFilters: boolean, clearFilters: () => void, onEdit: (row: DatasetRow) => void, pageSize: number, page: number, pageStart: number, totalPages: number, visiblePages: number[], setPage: SetPage}} props */
export function ProductDimensionTable({
  data,
  hasFilters,
  clearFilters,
  onEdit,
  page,
  pageSize,
  pageStart,
  totalPages,
  visiblePages,
  setPage,
}) {
  return (
    <>
      <ProductRowsTable
        data={data}
        hasFilters={hasFilters}
        clearFilters={clearFilters}
        onEdit={onEdit}
      />
      <ProductPagination
        page={page}
        pageSize={pageSize}
        pageStart={pageStart}
        totalPages={totalPages}
        visiblePages={visiblePages}
        setPage={setPage}
      />
    </>
  );
}
