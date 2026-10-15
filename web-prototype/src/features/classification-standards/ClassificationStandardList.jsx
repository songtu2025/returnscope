import {
  BookOpenText,
  CheckCircle,
  DotsThreeVertical,
  MagnifyingGlass,
  Plus,
  Tag,
  WarningCircle,
} from "@phosphor-icons/react";
import Button from "antd/es/button";
import Input from "antd/es/input";
import { EmptyState, InlineLoading, PageHeading } from "../../components/SharedUi";
import { useDismissibleDetails } from "../../hooks/useDismissibleDetails";
import { formatDate } from "../../lib/presentation";

/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardSummary} ClassificationStandardSummary */

/** @param {ClassificationStandardSummary} standard */
function statusLabel(standard) {
  if (standard.status === "active") return "使用中";
  return Number(standard.version_no) > 0 ? "已停用" : "尚未启用";
}

/**
 * @param {{
 *   standards: ClassificationStandardSummary[],
 *   error: string,
 *   hasData: boolean,
 *   loading: boolean,
 *   onRetry: () => void,
 *   totals: {active: number, categories: number, labels: number},
 *   query: string,
 *   statusFilter: "all" | "active" | "inactive",
 *   onQueryChange: (query: string) => void,
 *   onStatusChange: (status: "all" | "active" | "inactive") => void,
 *   onCreate: () => void,
 *   onView: (standard: ClassificationStandardSummary) => void,
 *   onDelete: (standard: ClassificationStandardSummary) => void,
 * }} props
 */
export function ClassificationStandardList({
  standards,
  error,
  hasData,
  loading,
  onRetry,
  totals,
  query,
  statusFilter,
  onQueryChange,
  onStatusChange,
  onCreate,
  onView,
  onDelete,
}) {
  return (
    <>
      <PageHeading
        title="分类标准"
        action={
          <Button type="primary" icon={<Plus size={16} />} onClick={onCreate}>
            新建分类标准
          </Button>
        }
      />
      {hasData && (
        <section className="standard-library-summary" aria-label="分类标准汇总">
          <div>
            <BookOpenText size={20} />
            <span>使用中标准</span>
            <strong>{totals.active}</strong>
          </div>
          <div>
            <CheckCircle size={20} />
            <span>覆盖品类</span>
            <strong>{totals.categories}</strong>
          </div>
          <div>
            <Tag size={20} />
            <span>分类标签</span>
            <strong>{totals.labels}</strong>
          </div>
        </section>
      )}
      <section className="standard-library-card" aria-busy={loading}>
        <div className="standard-library-toolbar">
          <Input
            className="standard-search-box"
            aria-label="搜索分类标准"
            prefix={<MagnifyingGlass size={17} />}
            placeholder="搜索标准名称或适用商品"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
          />
          <InlineLoading label="更新中…" compact active={loading && hasData} />
          <div className="standard-status-filter" role="group" aria-label="标准状态">
            {
              /** @type {const} */ ([
                ["all", "全部状态"],
                ["active", "使用中"],
                ["inactive", "未使用"],
              ]).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={statusFilter === value ? "active" : ""}
                  aria-pressed={statusFilter === value}
                  onClick={() => onStatusChange(value)}
                >
                  {label}
                </button>
              ))
            }
          </div>
        </div>
        {loading && !hasData && (
          <InlineLoading scope="page" label="正在读取分类标准…" />
        )}
        {error && (
          <div role="alert">
            <EmptyState
              icon={WarningCircle}
              title={
                hasData ? "分类标准更新失败，当前显示上一次数据" : "分类标准读取失败"
              }
              description={error}
              action={
                <button
                  className="secondary-button"
                  disabled={loading}
                  onClick={onRetry}
                >
                  重新加载
                </button>
              }
            />
          </div>
        )}
        {!loading && !error && standards.length === 0 && (
          <EmptyState
            icon={BookOpenText}
            title={
              query || statusFilter !== "all"
                ? "没有符合条件的分类标准"
                : "暂无分类标准"
            }
            description={
              query || statusFilter !== "all"
                ? "清除筛选后查看全部分类标准。"
                : "新建一套分类标准后即可用于分析任务。"
            }
            action={
              <button
                className="secondary-button"
                onClick={() => {
                  if (query || statusFilter !== "all") {
                    onQueryChange("");
                    onStatusChange("all");
                  } else onCreate();
                }}
              >
                {query || statusFilter !== "all" ? "清除筛选" : "新建分类标准"}
              </button>
            }
          />
        )}
        {standards.length > 0 && (
          <div className="standard-table-wrap">
            <table className="standard-library-table">
              <thead>
                <tr>
                  <th>分类标准</th>
                  <th>适用品类</th>
                  <th>标签体系</th>
                  <th>当前状态</th>
                  <th>最近更新</th>
                  <th aria-label="操作" />
                </tr>
              </thead>
              <tbody>
                {standards.map((standard) => (
                  <tr key={standard.id}>
                    <td>
                      <button
                        type="button"
                        className="standard-name-button"
                        onClick={() => onView(standard)}
                      >
                        <b>{standard.name}</b>
                        <span>{standard.product_context}</span>
                      </button>
                    </td>
                    <td>
                      <b>{standard.category_count}</b> 个品类
                    </td>
                    <td>
                      <b>{standard.label_count}</b> 个标签 ·{" "}
                      {standard.label_group_count} 组
                    </td>
                    <td>
                      <span className={`standard-status ${standard.status}`}>
                        {statusLabel(standard)}
                      </span>
                      {standard.draft_id && <small>有暂存修改</small>}
                    </td>
                    <td>{formatDate(standard.updated_at)}</td>
                    <td>
                      <StandardRowActions
                        standard={standard}
                        onView={onView}
                        onDelete={onDelete}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

/** @param {{standard: ClassificationStandardSummary, onView: (standard: ClassificationStandardSummary) => void, onDelete: (standard: ClassificationStandardSummary) => void}} props */
function StandardRowActions({ standard, onView, onDelete }) {
  const { detailsProps, summaryProps } = useDismissibleDetails({ menu: true });
  const actionLabel = standard.delete_mode === "delete" ? "删除标准" : "停用标准";
  return (
    <div className="standard-row-actions">
      <button type="button" onClick={() => onView(standard)}>
        查看
      </button>
      {(standard.status === "active" || standard.delete_mode === "delete") && (
        <details {...detailsProps} className="standard-more-menu">
          <summary
            {...summaryProps}
            aria-label={`更多标准操作：${standard.name}`}
            aria-haspopup="menu"
            title="更多标准操作"
          >
            <DotsThreeVertical size={17} />
          </summary>
          <div className="standard-row-menu" role="menu" aria-label="标准操作">
            <button
              type="button"
              role="menuitem"
              aria-label={`${actionLabel}：${standard.name}`}
              onClick={() => onDelete(standard)}
            >
              {actionLabel}
            </button>
          </div>
        </details>
      )}
    </div>
  );
}
