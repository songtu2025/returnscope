import { Pagination } from "../../components/Pagination";

/** @param {{query: string, search: string, total?: number, countError: boolean, matches: number, disabled: boolean, onQuery: (value: string) => void, onSearch: (value: string) => void, onRefresh: () => void, pagination: Parameters<typeof Pagination>[0]}} props */
export function TaskRecycleToolbar({
  query,
  search,
  total,
  countError,
  matches,
  disabled,
  onQuery,
  onSearch,
  onRefresh,
  pagination,
}) {
  return (
    <div className="recycle-toolbar">
      <form
        className="listing-queue-toolbar recycle-search-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!disabled) onSearch(query.trim());
        }}
      >
        <label className="listing-queue-search">
          <span>查找已移除的 Listing</span>
          <input
            aria-label="搜索回收站"
            placeholder="搜索 Listing、店铺或所属任务"
            value={query}
            onChange={(event) => onQuery(event.target.value)}
          />
        </label>
        <button className="secondary-button" disabled={disabled}>
          搜索
        </button>
        {(query || search) && (
          <button
            type="button"
            className="text-button"
            disabled={disabled}
            onClick={() => onSearch("")}
          >
            清除搜索
          </button>
        )}
        <button
          type="button"
          className="text-button"
          disabled={disabled}
          onClick={onRefresh}
        >
          刷新回收站
        </button>
      </form>
      <div className="recycle-toolbar-pagination">
        <p className="recycle-count" role="status" aria-label="回收站数量">
          {total === undefined
            ? countError
              ? "总数暂不可用"
              : "正在读取总数…"
            : `共 ${total.toLocaleString()} 条 · 第 ${pagination.page} 页`}
          {search && ` · 匹配 ${matches.toLocaleString()} 条 · 当前搜索：${search}`}
        </p>
        <fieldset
          className="recycle-pager"
          disabled={pagination.disabled}
          role="group"
          aria-label="回收站顶部分页"
        >
          <Pagination {...pagination} showTotal={false} />
        </fieldset>
      </div>
    </div>
  );
}
