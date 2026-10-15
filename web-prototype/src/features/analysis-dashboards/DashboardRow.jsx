import { CaretRight } from "@phosphor-icons/react";
import { formatTime } from "../../lib/presentation";
import { DeliveryLifecycleControls } from "../../components/DeliveryLifecycleControls";
/** @typedef {import("./analysisDashboardContracts").DashboardListItem} DashboardListItem */

/** @param {{dashboard: DashboardListItem, onOpen: () => void}} props */
export function DashboardRow({ dashboard, onOpen }) {
  const statusLabels = /** @type {Record<string, string>} */ ({
    active: "可用",
    archived: "已归档",
  });
  const summary = dashboard.summary ?? {};
  const status = dashboard.status || "active";
  return (
    <article className="dashboard-list-row" role="row">
      <span role="cell" className={`dashboard-status ${status}`}>
        {dashboard.deleted_at ? "已删除" : statusLabels[status] || status}
      </span>
      <div role="cell">
        <b>{dashboard.name || "未命名看板"}</b>
        {dashboard.description && <small>{dashboard.description}</small>}
      </div>
      <b role="cell">v{dashboard.current_version || dashboard.version || 1}</b>
      <span role="cell">
        {Number(summary.listing_count || 0).toLocaleString()} 个 Listing
      </span>
      <span role="cell" className="dashboard-record-count">
        <b>
          {Number(summary.comment_count ?? summary.record_count ?? 0).toLocaleString()}
        </b>{" "}
        <small>{summary.counting_basis === "feedback_group" ? "个反馈组" : "条"}</small>
      </span>
      <span role="cell">
        {formatTime(dashboard.updated_at || dashboard.created_at)}
      </span>
      <span role="cell">{dashboard.created_by_name || "未提供"}</span>
      <div role="cell" className="dashboard-row-actions">
        <button
          className="secondary-button compact-button"
          data-list-return-id={dashboard.id || dashboard.dashboard_id}
          onClick={onOpen}
        >
          查看 <CaretRight size={15} />
        </button>
        <DeliveryLifecycleControls
          kind="dashboard"
          id={dashboard.id || dashboard.dashboard_id || ""}
          name={dashboard.name || "未命名看板"}
          revision={dashboard.revision || 1}
          deleted={Boolean(dashboard.deleted_at)}
        />
      </div>
    </article>
  );
}
