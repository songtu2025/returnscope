import { WarningCircle } from "@phosphor-icons/react";
import { RESULT_PAGE_SIZES } from "./classificationResultConstants";

export function Pagination({ page, pageSize, total, totalPages, onPage, onPageSize }) {
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
          {RESULT_PAGE_SIZES.map((size) => (
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

export function ResultError({ message, onRetry }) {
  return (
    <div className="result-error-state" role="alert">
      <WarningCircle size={24} />
      <div>
        <b>分类结果读取失败</b>
        <p>{message}</p>
      </div>
      <button className="secondary-button" onClick={onRetry}>
        重试
      </button>
    </div>
  );
}
