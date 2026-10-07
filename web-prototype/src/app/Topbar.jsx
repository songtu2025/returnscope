import { MagnifyingGlass, SignOut } from "@phosphor-icons/react";

/** @typedef {import("./appContracts").CurrentUser} CurrentUser */
/** @typedef {import("./appContracts").SystemStatus} SystemStatus */
/** @typedef {import("./appContracts").Navigate} Navigate */

/** @param {{user: CurrentUser, system: SystemStatus | null, onRefresh: () => Promise<void>, onNavigate: Navigate, onSearch: () => void, onLogout: () => void | Promise<void>}} props */
export function Topbar({ user, system, onRefresh, onNavigate, onSearch, onLogout }) {
  return (
    <header className="topbar">
      <button
        className="topbar-search"
        onClick={onSearch}
        aria-label="查找任务、数据或复核记录"
        title="全局搜索（Ctrl K）"
      >
        <MagnifyingGlass size={18} />
        <span>查找任务、数据或复核记录</span>
        <kbd>Ctrl K</kbd>
      </button>
      <div className="topbar-actions">
        <button
          className="capacity-chip"
          onClick={async () => {
            await onRefresh();
            onNavigate("analysis-tasks");
          }}
          title="查看进行中的分析任务"
        >
          <span>我的运行 Listing</span>
          <strong>
            {system?.my_running_segments ?? system?.my_running_tasks ?? 0}/3
          </strong>
        </button>
        <div className="user-block" title={`${user.display_name} · ${user.email}`}>
          <span>{user.display_name?.slice(0, 1)}</span>
          <div>
            <b>{user.display_name}</b>
            <small>{user.email}</small>
          </div>
        </div>
        <button className="icon-button" onClick={onLogout} aria-label="退出登录">
          <SignOut size={20} />
        </button>
      </div>
    </header>
  );
}
