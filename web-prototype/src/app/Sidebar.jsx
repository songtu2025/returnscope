import { PRIMARY_NAV_ITEMS, SETTINGS_NAV_ITEM } from "./navigation";
import { classNames } from "../lib/presentation";
import { preloadPage } from "./pageModules";

/** @typedef {import("./navigation").NavigationItem} NavigationItem */
/** @typedef {import("./appContracts").SystemStatus} SystemStatus */
/** @typedef {import("./appContracts").Navigate} Navigate */

/** @param {{page: string, system: SystemStatus | null, onNavigate: Navigate}} props */
export function Sidebar({ page, system, onNavigate }) {
  const activePage =
    page === "legacy-results"
      ? "analysis-dashboards"
      : page === "task-create"
        ? "analysis-tasks"
        : page === "review" || page === "review-center"
          ? "classification-results"
          : page;
  const pendingReviewBatches = Number(
    system?.pending_review_batches ??
      system?.pending_review_batch_count ??
      system?.review_batch_pending_count ??
      0,
  );
  return (
    <aside className="sidebar">
      <div className="brand">
        <img src="/assets/brand-mark-160.png" alt="" />
        <div>
          <strong>用户语义分析</strong>
          <span>智能体工作台</span>
        </div>
      </div>
      <nav className="primary-nav" aria-label="主导航">
        {PRIMARY_NAV_ITEMS.map((item) => (
          <SidebarNavItem
            item={item}
            active={activePage === item.id}
            badge={item.id === "classification-results" ? pendingReviewBatches : null}
            onNavigate={onNavigate}
            key={item.id}
          />
        ))}
      </nav>
      <nav className="sidebar-utility-nav" aria-label="系统管理">
        <SidebarNavItem
          item={SETTINGS_NAV_ITEM}
          active={activePage === SETTINGS_NAV_ITEM.id}
          onNavigate={onNavigate}
        />
      </nav>
    </aside>
  );
}

/** @param {{item: NavigationItem, active: boolean, badge?: number | null, onNavigate: Navigate}} props */
function SidebarNavItem({
  item: { id, label, icon: Icon },
  active,
  badge = null,
  onNavigate,
}) {
  return (
    <button
      className={classNames("nav-item", active && "active")}
      onClick={() => onNavigate(id)}
      onMouseEnter={() => preloadPage(id)}
      onFocus={() => preloadPage(id)}
      aria-current={active ? "page" : undefined}
    >
      <Icon
        className="sidebar-nav-icon"
        size={20}
        weight={active ? "duotone" : "regular"}
        aria-hidden="true"
      />
      <span>{label}</span>
      {badge != null && badge > 0 && <em>{badge > 99 ? "99+" : badge}</em>}
    </button>
  );
}
