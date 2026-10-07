import { ArrowRight } from "@phosphor-icons/react";
import { navigateHash } from "../../app/hashRouter";
import { routeForTarget } from "../../app/navigation";
import { formatTime } from "../../lib/presentation";
import { AuditDiff } from "./AuditLogDiff";
import { writeAuditRoute } from "./auditLogPolicy";

/** @type {Record<string, string>} */
const ACTION_LABELS = {
  task_create: "创建任务",
  task_pause: "暂停任务",
  task_resume: "继续任务",
  task_cancel: "取消任务",
  segment_pause: "暂停 Listing",
  segment_resume: "继续 Listing",
  segment_cancel: "取消 Listing",
  segment_retry: "重试 Listing",
  review_update: "更新复核记录",
  review_batch_update: "更新复核批次",
  review_batch_publish: "发布复核版本",
  legacy_result_backfill_prepare: "准备回填历史结果",
  config_publish: "发布模型配置",
  user_update: "更新用户",
};
/** @type {Record<string, string>} */
const ENTITY_LABELS = {
  task: "分析任务",
  task_segment: "Listing 片段",
  review: "历史复核记录",
  review_batch: "复核批次",
  dataset: "数据资产",
  data_version: "数据版本",
  api_connection: "API 接入",
  config_version: "模型配置版本",
  model: "模型",
  user: "用户",
  classification_result: "分类结果",
  analysis_dashboard: "分析看板",
};
/** @param {{items: import("../../shared/api/systemSettingsContracts").AuditLogEntry[]}} props */
export function AuditLogEntries({ items }) {
  return (
    <div className="audit-list">
      {items.map((item) => (
        <AuditLogEntry key={item.id} item={item} />
      ))}
    </div>
  );
}

/** @param {{item: import("../../shared/api/systemSettingsContracts").AuditLogEntry}} props */
function AuditLogEntry({ item }) {
  return (
    <article>
      <header>
        <div>
          <b>{item.actor_name || "未提供操作人"}</b>
          <AuditTerm value={item.action} labels={ACTION_LABELS} fallback="未提供动作" />
        </div>
        <time>{formatTime(item.created_at)}</time>
      </header>
      <div className="audit-object-line">
        <span className="audit-object-identity">
          <AuditTerm
            value={item.entity_type}
            labels={ENTITY_LABELS}
            fallback="未提供对象"
          />
          <span>· {item.entity_id || "未提供 ID"}</span>
        </span>
        {item.target?.route && (
          <button
            className="text-button"
            onClick={() => {
              const destination = routeForTarget(item.target);
              if (destination) {
                navigateHash(destination.page, destination.query);
              }
            }}
          >
            查看对象 <ArrowRight size={14} />
          </button>
        )}
      </div>
      <AuditDiff before={item.before} after={item.after} />
    </article>
  );
}

/** @param {{value?: string, labels: Record<string, string>, fallback: string}} props */
function AuditTerm({ value, labels, fallback }) {
  if (!value) return <span>{fallback}</span>;
  const label = labels[value];
  return (
    <span className="audit-technical-term">
      {label ?? value}
      {label && <code>{value}</code>}
    </span>
  );
}

/** @param {{total: number, page: number, pages: number, route: import("./auditLogPolicy").AuditRoute}} props */
export function AuditLogPagination({ total, page, pages, route }) {
  return (
    <footer className="quality-pagination">
      <span>
        共 {total.toLocaleString()} 条 · 第 {page}/{pages} 页
      </span>
      <button
        className="secondary-button"
        disabled={page <= 1}
        onClick={() => writeAuditRoute(route, { page: page - 1 })}
      >
        上一页
      </button>
      <button
        className="secondary-button"
        disabled={page >= pages}
        onClick={() => writeAuditRoute(route, { page: page + 1 })}
      >
        下一页
      </button>
    </footer>
  );
}
