import {
  BookOpenText,
  CheckCircle,
  MagnifyingGlass,
  Plus,
  Tag,
} from "@phosphor-icons/react";
import { EmptyState, PageHeading } from "../../components/SharedUi";
import { formatDate } from "../../lib/presentation";

function statusLabel(standard) {
  if (standard.status === "active") return "使用中";
  return Number(standard.version_no) > 0 ? "已停用" : "未发布";
}

export function ClassificationStandardList({
  standards,
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
        eyebrow="语义分类治理"
        title="分类标准"
        description="维护商品品类与退货问题标签，分析任务会自动读取当前启用版本。"
        action={
          <button type="button" className="primary-button" onClick={onCreate}>
            <Plus size={16} /> 新建分类标准
          </button>
        }
      />
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
      <section className="standard-library-card">
        <div className="standard-library-toolbar">
          <label className="standard-search-box">
            <MagnifyingGlass size={17} />
            <input
              aria-label="搜索分类标准"
              placeholder="搜索标准名称或适用商品"
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
            />
          </label>
          <div className="standard-status-filter" role="group" aria-label="标准状态">
            {[
              ["all", "全部状态"],
              ["active", "使用中"],
              ["inactive", "未使用"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={statusFilter === value ? "active" : ""}
                aria-pressed={statusFilter === value}
                onClick={() => onStatusChange(value)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        {standards.length === 0 ? (
          <EmptyState
            icon={BookOpenText}
            title="没有符合条件的分类标准"
            description="调整搜索条件，或新建一套分类标准。"
          />
        ) : (
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
                      <small>
                        {Number(standard.version_no) > 0
                          ? `V${standard.version_no}`
                          : "草稿"}
                        {standard.draft_id && Number(standard.version_no) > 0
                          ? " · 有草稿"
                          : ""}
                      </small>
                    </td>
                    <td>{formatDate(standard.updated_at)}</td>
                    <td>
                      <div className="standard-row-actions">
                        <button type="button" onClick={() => onView(standard)}>
                          查看
                        </button>
                        {(standard.status === "active" ||
                          standard.delete_mode === "delete") && (
                          <button
                            type="button"
                            className="standard-deactivate-action"
                            aria-label={`${standard.delete_mode === "delete" ? "删除标准" : "停用标准"}：${standard.name}`}
                            onClick={() => onDelete(standard)}
                          >
                            {standard.delete_mode === "delete" ? "删除" : "停用"}
                          </button>
                        )}
                      </div>
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
