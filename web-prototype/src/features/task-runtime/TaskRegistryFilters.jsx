import { MagnifyingGlass, SlidersHorizontal, X } from "@phosphor-icons/react";

/** @typedef {import("./taskMonitorContracts").TaskListState} TaskListState */
/**
 * @typedef {Object} TaskRegistryFiltersProps
 * @property {TaskListState} viewState
 * @property {(changes: Partial<TaskListState>) => void} onViewStateChange
 * @property {string[]} owners
 * @property {Record<string, number>} counts
 * @property {import("react").RefObject<HTMLInputElement | null>} searchInputRef
 */
const FILTERS = [
  ["all", "全部"],
  ["active", "未结束"],
  ["finished", "已结束"],
  ["archived", "已归档"],
];

/** @param {Pick<TaskRegistryFiltersProps, "viewState" | "onViewStateChange" | "owners">} props */
function RegistrySortMenu({ viewState, onViewStateChange, owners }) {
  const { owner, sort } = viewState;
  return (
    <details className="task-registry-filter-menu">
      <summary>
        <SlidersHorizontal size={17} /> 筛选与排序{owner !== "all" ? " · 1" : ""}
      </summary>
      <div className="task-registry-controls">
        <select
          value={owner}
          onChange={(event) => onViewStateChange({ owner: event.target.value })}
          aria-label="按负责人筛选"
        >
          <option value="all">全部负责人</option>
          {owners.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <select
          value={sort}
          onChange={(event) => onViewStateChange({ sort: event.target.value })}
          aria-label="任务排序"
        >
          <option value="updated_desc">最近更新</option>
          <option value="created_desc">最近创建</option>
          <option value="progress_desc">进度从高到低</option>
        </select>
      </div>
    </details>
  );
}

/** @param {Omit<TaskRegistryFiltersProps, "counts">} props */
function RegistrySearch({ viewState, onViewStateChange, owners, searchInputRef }) {
  const { query } = viewState;
  return (
    <div className="task-registry-toolbar">
      <label className="task-registry-search">
        <MagnifyingGlass size={18} />
        <input
          ref={searchInputRef}
          value={query}
          onChange={(event) => onViewStateChange({ query: event.target.value })}
          placeholder="搜索任务、店铺或 Listing"
          aria-label="搜索任务、店铺或 Listing"
        />
        {query && (
          <button
            type="button"
            onClick={() => {
              onViewStateChange({ query: "" });
              searchInputRef.current?.focus();
            }}
            aria-label="清空搜索"
          >
            <X size={15} />
          </button>
        )}
      </label>
      <RegistrySortMenu
        viewState={viewState}
        onViewStateChange={onViewStateChange}
        owners={owners}
      />
    </div>
  );
}

/** @param {Pick<TaskRegistryFiltersProps, "viewState" | "onViewStateChange" | "counts">} props */
function RegistryTabs({ viewState, onViewStateChange, counts }) {
  const { filter, attentionOnly } = viewState;
  return (
    <div className="task-registry-tabs" aria-label="任务筛选">
      {FILTERS.map(([value, label]) => (
        <button
          key={value}
          className={filter === value ? "active" : ""}
          onClick={() => onViewStateChange({ filter: value })}
          aria-pressed={filter === value}
          aria-label={label}
        >
          {label}
          <span>{counts[value]}</span>
        </button>
      ))}
      <label className="task-attention-filter">
        <input
          type="checkbox"
          checked={attentionOnly}
          onChange={(event) =>
            onViewStateChange({ attentionOnly: event.target.checked })
          }
        />
        只看需处理
      </label>
    </div>
  );
}

/** @param {TaskRegistryFiltersProps} props */
export function TaskRegistryFilters(props) {
  return (
    <>
      <RegistrySearch
        viewState={props.viewState}
        onViewStateChange={props.onViewStateChange}
        owners={props.owners}
        searchInputRef={props.searchInputRef}
      />
      <RegistryTabs
        viewState={props.viewState}
        onViewStateChange={props.onViewStateChange}
        counts={props.counts}
      />
    </>
  );
}
