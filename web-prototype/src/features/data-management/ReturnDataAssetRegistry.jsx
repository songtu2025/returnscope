import {
  CaretDown,
  CaretLeft,
  CaretRight,
  CheckCircle,
  Database,
  Funnel,
  MagnifyingGlass,
  WarningCircle,
} from "@phosphor-icons/react";
import Input from "antd/es/input";
import { useRef } from "react";
import { formatTime } from "../../lib/presentation";
import {
  dataStatus,
  sourceDisplayName,
  sourceScopeLabel,
} from "./returnDataAssetPresentation";

/** @typedef {import("../../shared/api/dataManagementContracts").DatasetSource} DatasetSource */
/** @typedef {(changes: Record<string, string | number>) => void} RouteChange */
/** @typedef {{sourceCount: number, availableCount: number, latestUpdate: string}} SummaryProps */
/** @typedef {{query: string, status: string | undefined, onRouteChange: RouteChange}} FilterProps */
/** @typedef {{page: number, totalPages: number, filteredCount: number, onRouteChange: RouteChange}} PaginationProps */
/** @typedef {{source: DatasetSource, expanded: boolean, selectSource: (source: DatasetSource) => void}} RowProps */
/** @typedef {RowProps & {expandedContent: import("react").ReactNode}} RecordProps */
/** @typedef {SummaryProps & FilterProps & PaginationProps & {visibleSources: DatasetSource[], expandedId: string, expandedContent: import("react").ReactNode, selectSource: (source: DatasetSource) => void}} RegistryProps */

/** @param {SummaryProps} props */
function RegistrySummary({ sourceCount, availableCount, latestUpdate }) {
  return (
    <div className="returns-registry-summary">
      <span>
        <Database size={18} />
        <b>{sourceCount} 个数据源</b>
      </span>
      <i aria-hidden="true">•</i>
      <strong>{availableCount} 个当前可用</strong>
      <i aria-hidden="true">•</i>
      <em>{sourceCount - availableCount} 个需关注</em>
      <i aria-hidden="true">•</i>
      <span>最近导入：{formatTime(latestUpdate)}</span>
    </div>
  );
}

/** @param {FilterProps} props */
function RegistryFilters({ query, status, onRouteChange }) {
  return (
    <div className="returns-registry-filters">
      <Input
        className="returns-registry-search"
        aria-label="搜索用户反馈数据源"
        prefix={<MagnifyingGlass size={17} />}
        value={query}
        onChange={(event) => onRouteChange({ q: event.target.value, page: 1 })}
        placeholder="搜索数据源或业务范围"
      />
      <label className="returns-registry-filter">
        <Funnel size={17} />
        <select
          aria-label="按数据状态筛选"
          value={status}
          onChange={(event) => onRouteChange({ status: event.target.value, page: 1 })}
        >
          <option value="all">全部状态</option>
          <option value="available">当前可用</option>
          <option value="attention">需关注</option>
        </select>
      </label>
    </div>
  );
}

/** @param {{source: DatasetSource}} props */
function RegistrySourceStatus({ source }) {
  const sourceState = dataStatus(source);
  return (
    <span className={`returns-source-status ${sourceState.value}`}>
      {sourceState.value === "available" ? (
        <CheckCircle size={18} weight="fill" />
      ) : (
        <WarningCircle size={18} weight="fill" />
      )}
      <span>
        <b>{sourceState.label}</b>
        <small>{sourceState.description}</small>
      </span>
    </span>
  );
}

/** @param {RowProps} props */
function RegistryRow({ source, expanded, selectSource }) {
  return (
    <div className="returns-registry-row" role="row">
      <div className="returns-registry-name">
        <Database size={19} weight="duotone" />
        <b>{sourceDisplayName(source)}</b>
      </div>
      <span>{sourceScopeLabel(source)}</span>
      <b>{Number(source.row_count || 0).toLocaleString()} 行</b>
      <span>{formatTime(source.updated_at)}</span>
      <RegistrySourceStatus source={source} />
      <span>{Number(source.task_reference_count || 0).toLocaleString()} 个任务</span>
      <button
        className="returns-detail-button"
        aria-expanded={expanded}
        onClick={() => selectSource(source)}
      >
        {expanded ? "收起详情" : "查看详情"}
        <CaretDown size={17} />
      </button>
    </div>
  );
}

/** @param {RecordProps} props */
function RegistryRecord({ source, expanded, selectSource, expandedContent }) {
  return (
    <article className={`returns-registry-record ${expanded ? "expanded" : ""}`}>
      <RegistryRow source={source} expanded={expanded} selectSource={selectSource} />
      {expanded && expandedContent}
    </article>
  );
}

/** @param {PaginationProps} props */
function RegistryPagination({ page, totalPages, filteredCount, onRouteChange }) {
  const pageRef = useRef(/** @type {HTMLElement | null} */ (null));
  return (
    <footer className="returns-registry-footer">
      <span>共 {filteredCount} 个数据源</span>
      {totalPages > 1 && (
        <div>
          <button
            aria-label="上一页"
            disabled={page === 1}
            onClick={() => {
              if (page === 2) pageRef.current?.focus();
              onRouteChange({ page: page - 1 });
            }}
          >
            <CaretLeft size={16} />
          </button>
          <b ref={pageRef} tabIndex={-1} aria-label={`第 ${page} 页`}>
            {page}
          </b>
          <span>/ {totalPages}</span>
          <button
            aria-label="下一页"
            disabled={page === totalPages}
            onClick={() => {
              if (page + 1 === totalPages) pageRef.current?.focus();
              onRouteChange({ page: page + 1 });
            }}
          >
            <CaretRight size={16} />
          </button>
        </div>
      )}
    </footer>
  );
}

/** @param {RegistryProps} props */
function RegistryTable({ visibleSources, expandedId, expandedContent, selectSource }) {
  return visibleSources.length ? (
    <div className="returns-registry-table" role="table">
      <div className="returns-registry-head" role="row">
        <span>数据源</span>
        <span>业务范围</span>
        <span>当前数据</span>
        <span>最近导入</span>
        <span>数据状态</span>
        <span>被任务使用</span>
        <span>操作</span>
      </div>
      {visibleSources.map((source) => (
        <RegistryRecord
          key={source.id}
          source={source}
          expanded={source.id === expandedId}
          expandedContent={expandedContent}
          selectSource={selectSource}
        />
      ))}
    </div>
  ) : (
    <div className="returns-registry-empty">
      <MagnifyingGlass size={23} />
      <b>没有符合条件的数据源</b>
      <span>请修改搜索词或数据状态。</span>
    </div>
  );
}

/** @param {RegistryProps} props */
export function ReturnDataAssetRegistry(props) {
  return (
    <section className="returns-registry" aria-label="用户反馈数据源清单">
      <header className="returns-registry-toolbar">
        <RegistrySummary
          sourceCount={props.sourceCount}
          availableCount={props.availableCount}
          latestUpdate={props.latestUpdate}
        />
        <RegistryFilters
          query={props.query}
          status={props.status}
          onRouteChange={props.onRouteChange}
        />
      </header>
      <RegistryTable {...props} />
      <RegistryPagination
        page={props.page}
        totalPages={props.totalPages}
        filteredCount={props.filteredCount}
        onRouteChange={props.onRouteChange}
      />
    </section>
  );
}
