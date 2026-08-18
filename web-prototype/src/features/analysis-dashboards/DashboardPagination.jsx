const PAGE_SIZES = [20, 50, 100];

export function DashboardPagination({
  page,
  pageSize,
  total,
  totalPages,
  onPage,
  onPageSize,
}) {
  return (
    <div className="result-pagination">
      <span>共 {Number(total || 0).toLocaleString()} 条</span>
      <label>
        每页
        <select
          aria-label="每页数量"
          value={pageSize}
          onChange={(event) => onPageSize(Number(event.target.value))}
        >
          {PAGE_SIZES.map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
      </label>
      <button
        className="secondary-button compact-button"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
      >
        上一页
      </button>
      <b>
        {page} / {totalPages}
      </b>
      <button
        className="secondary-button compact-button"
        disabled={page >= totalPages}
        onClick={() => onPage(page + 1)}
      >
        下一页
      </button>
    </div>
  );
}
