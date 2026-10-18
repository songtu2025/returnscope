/** @type {Record<string, string>} */
const EVENT_TYPE_LABELS = {
  created: "创建任务",
  updated: "修改任务",
  status_changed: "状态变化",
  cancel: "取消任务",
  pause: "暂停任务",
  resume: "继续任务",
  recovered: "服务恢复",
  progress: "运行进度",
  segment_progress: "Listing 进度",
  segment_started: "Listing 开始",
  segment_cancel: "取消 Listing",
  segment_pause: "暂停 Listing",
  segment_resume: "继续 Listing",
  segment_delete: "移除 Listing",
  segment_restore: "恢复 Listing",
  segment_remove_requested: "请求移除 Listing",
  segment_removed: "Listing 已移除",
  segment_purge: "永久删除 Listing",
  segment_retry: "重试 Listing",
  segment_completed: "Listing 完成",
  segment_completed_with_errors: "Listing 完成但有失败项",
  segment_failed: "Listing 失败",
  segment_paused: "Listing 已暂停",
  segment_cancelled: "Listing 已取消",
  segments_reordered: "调整执行顺序",
  parallelism_changed: "调整并行数",
  result_published: "发布分类结果",
  result_publish_failed: "分类结果发布失败",
  segment_classified_publish_failed: "分类完成但发布失败",
  result_merge_failed: "结果汇总失败",
  legacy_export_failed: "兼容文件生成失败",
  legacy_result_backfill_started: "历史结果回填",
  model_service_paused: "模型异常暂停",
  review: "人工复核",
};

/** @typedef {{query: string, listing: string, type: string}} TaskEventFilterValues */
/** @param {{filters: TaskEventFilterValues, listings: {key: string, label: string, store?: string}[], types: string[], onChange: (value: TaskEventFilterValues) => void, filtered: boolean, count: number, total: number}} props */
export function TaskEventFilters({
  filters,
  listings,
  types,
  onChange,
  filtered,
  count,
  total,
}) {
  return (
    <div className="task-event-filter-panel">
      <div className="task-event-filters" role="group" aria-label="运行日志筛选">
        <label>
          关键词
          <input
            type="search"
            aria-label="搜索运行日志"
            placeholder="搜索消息、Listing、操作人或原因"
            value={filters.query}
            onChange={(event) => onChange({ ...filters, query: event.target.value })}
          />
        </label>
        <label>
          Listing
          <select
            aria-label="日志 Listing"
            value={filters.listing}
            onChange={(event) => onChange({ ...filters, listing: event.target.value })}
          >
            <option value="">全部 Listing</option>
            {listings.map((item) => (
              <option key={item.key} value={item.key}>
                {item.label}
                {item.store ? ` · ${item.store}` : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          事件类型
          <select
            aria-label="日志事件类型"
            value={filters.type}
            onChange={(event) => onChange({ ...filters, type: event.target.value })}
          >
            <option value="">全部事件</option>
            {types.map((type) => (
              <option key={type} value={type}>
                {EVENT_TYPE_LABELS[type] || `其他事件（${type}）`}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="task-event-filter-summary">
        <span role="status">
          {filtered ? `匹配 ${count} / ${total} 条` : `共 ${total} 条日志`}
        </span>
        <button
          type="button"
          className="secondary-button"
          disabled={!filtered}
          onClick={() => onChange({ query: "", listing: "", type: "" })}
        >
          重置日志筛选
        </button>
      </div>
    </div>
  );
}
