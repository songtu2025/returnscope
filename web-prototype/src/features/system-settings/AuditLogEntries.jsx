import { useId, useState } from "react";
import {
  ACTION_LABELS,
  auditObjectLabel,
  auditObjectName,
} from "./auditLogPresentation";
import { ArrowRight } from "@phosphor-icons/react";
import { navigateHash } from "../../app/hashRouter";
import { routeForTarget } from "../../app/navigation";
import { formatTime } from "../../lib/presentation";
import { AuditDiff } from "./AuditLogDiff";
import { writeAuditRoute } from "./auditLogPolicy";

/** @param {{items: import("../../shared/api/systemSettingsContracts").AuditLogEntry[]}} props */
export function AuditLogEntries({ items }) {
  return (
    <div className="audit-table-wrap">
      <table className="audit-table" aria-label="审计记录列表">
        <thead>
          <tr>
            <th scope="col">时间</th>
            <th scope="col">操作人</th>
            <th scope="col">操作</th>
            <th scope="col">对象</th>
            <th scope="col">详情</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <AuditLogEntry key={item.id} item={item} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** @param {{item: import("../../shared/api/systemSettingsContracts").AuditLogEntry}} props */
function AuditLogEntry({ item }) {
  const [expanded, setExpanded] = useState(false);
  const detailId = useId();
  const destination = item.target ? routeForTarget(item.target) : null;
  return (
    <>
      <tr className={expanded ? "is-expanded" : undefined}>
        <td>
          <time>{formatTime(item.created_at)}</time>
        </td>
        <td>{item.actor_name || "未提供操作人"}</td>
        <td>{ACTION_LABELS[item.action ?? ""] ?? item.action ?? "未提供动作"}</td>
        <td>
          <b>{auditObjectLabel(item)}</b>
          <span className="audit-object-name" title={auditObjectName(item)}>
            {auditObjectName(item)}
          </span>
        </td>
        <td className="audit-row-actions">
          {destination && (
            <button
              className="text-button"
              onClick={() => navigateHash(destination.page, destination.query)}
            >
              查看对象 <ArrowRight size={14} />
            </button>
          )}
          <button
            className="text-button"
            aria-expanded={expanded}
            aria-controls={detailId}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? "收起详情" : "查看详情"}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="audit-detail-row">
          <td colSpan={5}>
            <div id={detailId} className="audit-entry-detail">
              <dl className="audit-entry-meta">
                <div>
                  <dt>对象名称</dt>
                  <dd>{auditObjectName(item)}</dd>
                </div>
                <div>
                  <dt>对象 ID</dt>
                  <dd>{item.entity_id || "--"}</dd>
                </div>
                <div>
                  <dt>对象类型</dt>
                  <dd>
                    <code>{item.entity_type || "--"}</code>
                  </dd>
                </div>
                <div>
                  <dt>操作代码</dt>
                  <dd>
                    <code>{item.action || "--"}</code>
                  </dd>
                </div>
              </dl>
              <AuditDiff before={item.before} after={item.after} />
            </div>
          </td>
        </tr>
      )}
    </>
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
