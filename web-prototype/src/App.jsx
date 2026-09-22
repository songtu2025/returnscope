import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { SWRConfig } from "swr";
import {
  Pulse,
  ArrowRight,
  CaretRight,
  Database,
  ListChecks,
  MagnifyingGlass,
  PlayCircle,
  SignOut,
  WarningCircle,
} from "@phosphor-icons/react";
import { ApiError, api } from "./api";
import { AppShell } from "./app/AppShell";
import { navigateHash, useHashRoute } from "./app/hashRouter";
import { PRIMARY_NAV_ITEMS, SETTINGS_NAV_ITEM } from "./app/navigation";
import { InlineLoading, PageLoadingState } from "./components/SharedUi";
import { Toast } from "./components/Toast";
import { STATUS_LABELS } from "./constants";
import { useDialogFocus } from "./hooks/useDialogFocus";
import { classNames } from "./lib/presentation";
import { SESSION_EXPIRED_EVENT } from "./shared/api/request";
import { serverStateConfig } from "./shared/serverState";
import { AuthPages } from "./pages/AuthPages";

const loadWorkbenchPage = () =>
  import("./features/workbench/WorkbenchPage").then((module) => ({
    default: module.WorkbenchPage,
  }));
const WorkbenchPage = lazy(loadWorkbenchPage);
const loadTaskCreatePage = () =>
  import("./features/task-create/TaskCreatePage").then((module) => ({
    default: module.TaskCreatePage,
  }));
const TaskCreatePage = lazy(loadTaskCreatePage);
const loadTaskRuntimePage = () =>
  import("./features/task-runtime/TaskRuntimePage").then((module) => ({
    default: module.TaskRuntimePage,
  }));
const TaskRuntimePage = lazy(loadTaskRuntimePage);
const ReviewCenter = lazy(() =>
  import("./pages/ReviewCenter").then((module) => ({
    default: module.ReviewCenter,
  })),
);
const loadDataAssetsPage = () =>
  import("./features/data-management/DataAssetsPage").then((module) => ({
    default: module.DataAssetsPage,
  }));
const DataAssetsPage = lazy(loadDataAssetsPage);
const loadClassificationStandardsPage = () =>
  import("./features/classification-standards/ClassificationStandardsPage").then(
    (module) => ({ default: module.ClassificationStandardsPage }),
  );
const ClassificationStandardsPage = lazy(loadClassificationStandardsPage);
const ResultsPage = lazy(() =>
  import("./pages/ResultsPage").then((module) => ({ default: module.ResultsPage })),
);
const loadClassificationResultsPage = () =>
  import("./pages/ClassificationResultsPage").then((module) => ({
    default: module.ClassificationResultsPage,
  }));
const ClassificationResultsPage = lazy(loadClassificationResultsPage);
const loadAnalysisDashboardPage = () =>
  import("./features/analysis-dashboards/AnalysisDashboardPage").then((module) => ({
    default: module.AnalysisDashboardPage,
  }));
const AnalysisDashboardPage = lazy(loadAnalysisDashboardPage);
const loadSystemSettingsPage = () =>
  import("./features/system-settings/SystemSettingsPage").then((module) => ({
    default: module.SystemSettingsPage,
  }));
const SystemSettingsPage = lazy(loadSystemSettingsPage);
const PUBLIC_AUTH_PAGES = new Set([
  "login",
  "forgot-password",
  "register",
  "reset-password",
  "change-email",
]);

/** @type {Record<string, () => Promise<unknown>>} */
const PAGE_PRELOADERS = {
  workbench: loadWorkbenchPage,
  "data-assets": loadDataAssetsPage,
  "classification-standards": loadClassificationStandardsPage,
  "analysis-tasks": loadTaskRuntimePage,
  "classification-results": loadClassificationResultsPage,
  "analysis-dashboards": loadAnalysisDashboardPage,
  settings: loadSystemSettingsPage,
};

/** @param {string} page */
function preloadPage(page) {
  const loader = PAGE_PRELOADERS[page];
  if (loader) void loader();
}

/** @typedef {import("./app/navigation").NavigationFocus} NavigationFocus */
/** @typedef {import("./app/navigation").NavigationItem} NavigationItem */
/** @typedef {{id: string, email: string, display_name: string, is_admin?: boolean}} CurrentUser */
/** @typedef {{warnings?: string[], pending_review_batches?: number, pending_review_batch_count?: number, review_batch_pending_count?: number, my_running_segments?: number, my_running_tasks?: number}} SystemStatus */
/** @typedef {{message: string, tone: string}} ToastState */
/** @typedef {(message: string, tone?: string) => void} Notify */
/** @typedef {(destination: string, focus?: NavigationFocus | null) => void} Navigate */
/** @typedef {{id: string, title: string, owner_name: string, status: keyof typeof STATUS_LABELS, store: string, listing?: string}} SearchTask */
/** @typedef {{id: string, kind: string, name: string, current_version: number, row_count: number, description?: string}} SearchDataset */
/** @typedef {{id: string, workflow_status: string, comment: string, task_title: string, owner_name: string}} SearchReview */
/** @typedef {{tasks: SearchTask[], datasets: SearchDataset[], reviews: SearchReview[]}} SearchResources */
/** @typedef {{id: string, type: string, icon: import("react").ElementType, title: string, meta: string, keywords: string, page: string, focus: NavigationFocus}} GlobalSearchItem */

/** @param {unknown} error */
function errorMessage(error) {
  return error instanceof Error ? error.message : "请求失败";
}

function App() {
  const [user, setUser] = useState(/** @type {CurrentUser | null} */ (null));
  const [booting, setBooting] = useState(true);
  const [system, setSystem] = useState(/** @type {SystemStatus | null} */ (null));
  const [toast, setToast] = useState(/** @type {ToastState | null} */ (null));
  const [searchOpen, setSearchOpen] = useState(false);
  const { route, navigate } = useHashRoute();

  const notify = useCallback(
    /** @type {Notify} */
    (message, tone = "success") => {
      setToast({ message, tone });
      window.setTimeout(() => setToast(null), 3200);
    },
    [],
  );

  useEffect(() => {
    const handleSessionExpired = () => {
      setUser(null);
      setSystem(null);
      setSearchOpen(false);
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
    return () =>
      window.removeEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
  }, []);

  const refreshSystem = useCallback(async () => {
    try {
      setSystem(await api.status());
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) setUser(null);
    }
  }, []);

  useEffect(() => {
    api
      .me()
      .then((value) => {
        setUser(value);
        return api.status();
      })
      .then(setSystem)
      .catch(() => setUser(null))
      .finally(() => setBooting(false));
  }, []);

  useEffect(() => {
    const handleShortcut = (/** @type {KeyboardEvent} */ event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (user) setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, [user]);

  useEffect(() => {
    if (user && PUBLIC_AUTH_PAGES.has(route.page) && route.page !== "change-email") {
      navigateHash("workbench", {}, { replace: true });
    }
  }, [route.page, user]);

  if (booting) return <LoadingScreen />;
  if (!user || route.page === "change-email") {
    return (
      <AuthPages
        route={route}
        onLogin={(value) => {
          setUser(value);
          refreshSystem();
        }}
        onSessionEnded={() => {
          setUser(null);
          setSystem(null);
        }}
      />
    );
  }
  if (PUBLIC_AUTH_PAGES.has(route.page)) return <LoadingScreen />;

  const page = route.page;
  return (
    <SWRConfig key={user.id} value={serverStateConfig}>
      <AppShell
        sidebar={<Sidebar page={page} system={system} onNavigate={navigate} />}
        topbar={
          <Topbar
            user={user}
            system={system}
            onRefresh={refreshSystem}
            onNavigate={navigate}
            onSearch={() => setSearchOpen(true)}
            onLogout={async () => {
              await api.logout();
              setUser(null);
            }}
          />
        }
        warning={
          system?.warnings && system.warnings.length > 0 ? (
            <div className="system-warning">
              <WarningCircle size={17} />
              <span>
                上线前安全检查：{system.warnings.join("；")}
                。请前往系统设置修改密码，并在生产环境设置独立加密密钥。
              </span>
              <button
                className="text-button"
                onClick={() =>
                  navigateHash("settings", { tab: "users", action: "password" })
                }
              >
                修改密码
                <ArrowRight size={14} />
              </button>
            </div>
          ) : null
        }
        overlays={
          <>
            {searchOpen && (
              <GlobalSearch
                onClose={() => setSearchOpen(false)}
                onSelect={(destination, focus) => {
                  setSearchOpen(false);
                  navigate(destination, focus);
                }}
                notify={notify}
              />
            )}
            {toast && <Toast {...toast} />}
          </>
        }
      >
        <Suspense
          fallback={
            <div className="standard-page">
              <PageLoadingState label="正在加载页面…" />
            </div>
          }
        >
          {page === "workbench" && <WorkbenchPage onNavigate={navigate} />}
          {page === "task-create" && (
            <TaskCreatePage
              route={route}
              onNavigate={navigate}
              notify={notify}
              onChanged={refreshSystem}
              userId={user.id}
            />
          )}
          {page === "analysis-tasks" && (
            <TaskRuntimePage
              route={route}
              notify={notify}
              onNavigate={navigate}
              onChanged={refreshSystem}
            />
          )}
          {page === "review" && (
            <>
              <div className="legacy-review-notice" role="status">
                <div>
                  <b>旧版单记录复核</b>
                  <span>仅用于历史任务，与新版复核批次和派生版本相互独立。</span>
                </div>
                <button
                  className="secondary-button"
                  onClick={() => navigate("review-center")}
                >
                  进入分类结果复核记录
                </button>
              </div>
              <ReviewCenter
                notify={notify}
                onChanged={refreshSystem}
                focus={
                  route.query.review
                    ? {
                        kind: "review",
                        id: route.query.review,
                        status: route.query.status,
                      }
                    : null
                }
              />
            </>
          )}
          {page === "data-assets" && (
            <DataAssetsPage
              route={route}
              notify={notify}
              onNavigate={navigate}
              userId={user.id}
            />
          )}
          {page === "classification-standards" && (
            <ClassificationStandardsPage route={route} notify={notify} />
          )}
          {page === "legacy-results" && (
            <Suspense fallback={<InlineLoading label="正在加载旧版任务分析…" />}>
              <div className="legacy-results-notice" role="status">
                <div>
                  <b>旧版任务分析</b>
                  <span>此页面仅用于兼容历史任务，不是新版分析看板。</span>
                </div>
                <div className="legacy-results-actions">
                  <button
                    className="secondary-button"
                    onClick={() => navigate("analysis-dashboards")}
                  >
                    进入新版分析看板
                  </button>
                  <button
                    className="secondary-button"
                    onClick={() => navigate("classification-results")}
                  >
                    查看分类结果
                  </button>
                </div>
              </div>
              <ResultsPage
                notify={notify}
                onNavigate={navigate}
                focus={
                  route.query.task_id
                    ? {
                        kind: "result",
                        id: route.query.task_id,
                        listing: route.query.listing,
                      }
                    : null
                }
              />
            </Suspense>
          )}
          {page === "classification-results" && (
            <Suspense
              fallback={
                <div className="standard-page classification-results-page">
                  <PageLoadingState label="正在加载分类结果池…" />
                </div>
              }
            >
              <ClassificationResultsPage
                notify={notify}
                route={route}
                userId={user.id}
              />
            </Suspense>
          )}
          {page === "analysis-dashboards" && (
            <AnalysisDashboardPage route={route} notify={notify} userId={user.id} />
          )}
          {page === "settings" && (
            <SystemSettingsPage route={route} notify={notify} currentUser={user} />
          )}
        </Suspense>
      </AppShell>
    </SWRConfig>
  );
}

function LoadingScreen() {
  return (
    <div className="loading-screen">
      <div className="brand-orb">
        <Pulse size={28} weight="bold" />
      </div>
      <strong>正在连接智能体工作台</strong>
      <span>读取任务与运行状态…</span>
    </div>
  );
}

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
        <img src="/assets/brand-mark.png" alt="" />
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

/** @param {{onClose: () => void, onSelect: Navigate, notify: Notify}} props */
function GlobalSearch({ onClose, onSelect, notify }) {
  const [query, setQuery] = useState("");
  const [resources, setResources] = useState(
    /** @type {SearchResources} */ ({
      tasks: [],
      datasets: [],
      reviews: [],
    }),
  );
  const [loading, setLoading] = useState(false);
  const { dialogRef, constrainFocus } = useDialogFocus({ open: true, onClose });

  useEffect(() => {
    setLoading(true);
    Promise.all([api.tasks(), api.datasets(), api.reviews()])
      .then(([tasks, datasets, reviews]) => setResources({ tasks, datasets, reviews }))
      .catch((error) => notify(errorMessage(error), "error"))
      .finally(() => setLoading(false));
  }, [notify]);

  /** @type {GlobalSearchItem[]} */
  const items = [
    ...resources.tasks.map(
      /** @returns {GlobalSearchItem} */ (task) => ({
        id: task.id,
        type: "任务",
        icon: PlayCircle,
        title: task.title,
        meta: `${task.owner_name} · ${STATUS_LABELS[task.status] ?? task.status}`,
        keywords: `${task.title} ${task.store} ${task.listing ?? ""} ${task.owner_name}`,
        page: task.status === "completed" ? "legacy-results" : "analysis-tasks",
        focus: {
          kind: task.status === "completed" ? "result" : "task",
          id: task.id,
        },
      }),
    ),
    ...resources.datasets
      .filter((dataset) => dataset.kind === "products")
      .map(
        /** @returns {GlobalSearchItem} */ (dataset) => ({
          id: dataset.id,
          type: "产品信息",
          icon: Database,
          title: dataset.name,
          meta: `v${dataset.current_version} · ${dataset.row_count.toLocaleString()} 行`,
          keywords: `${dataset.name} ${dataset.description ?? ""} ${dataset.kind}`,
          page: "data-assets",
          focus: { kind: "dataset", id: dataset.id, datasetKind: dataset.kind },
        }),
      ),
    ...resources.reviews.map(
      /** @returns {GlobalSearchItem} */ (review) => ({
        id: review.id,
        type: review.workflow_status === "pending" ? "待复核" : "已复核",
        icon: ListChecks,
        title: review.comment,
        meta: `${review.task_title} · ${review.owner_name}`,
        keywords: `${review.comment} ${review.task_title} ${review.owner_name}`,
        page: "review",
        focus: { kind: "review", id: review.id, status: review.workflow_status },
      }),
    ),
  ];
  const normalized = query.trim().toLowerCase();
  const matches = items
    .filter(
      (item) =>
        !normalized ||
        `${item.title} ${item.keywords}`.toLowerCase().includes(normalized),
    )
    .slice(0, 12);

  return (
    <div
      className="command-backdrop"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <section
        ref={dialogRef}
        className="command-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="全局搜索"
        tabIndex={-1}
        onKeyDownCapture={constrainFocus}
      >
        <header>
          <MagnifyingGlass size={20} />
          <input
            aria-label="全局搜索"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && matches[0])
                onSelect(matches[0].page, matches[0].focus);
            }}
            placeholder="输入任务名、产品信息或评论…"
            data-dialog-initial-focus
          />
          <kbd>Esc</kbd>
        </header>
        <div className="command-results">
          {loading && (
            <div className="command-empty">
              <Pulse size={22} />
              正在读取工作区…
            </div>
          )}
          {!loading && matches.length === 0 && (
            <div className="command-empty">
              <MagnifyingGlass size={22} />
              没有找到匹配内容
            </div>
          )}
          {!loading &&
            matches.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={`${item.type}-${item.id}`}
                  onClick={() => onSelect(item.page, item.focus)}
                >
                  <span>
                    <Icon size={19} />
                  </span>
                  <div>
                    <b>{item.title}</b>
                    <small>{item.meta}</small>
                  </div>
                  <em>{item.type}</em>
                  <CaretRight size={16} />
                </button>
              );
            })}
        </div>
        <footer>
          <span>输入关键词筛选</span>
          <span>
            <kbd>Enter</kbd> 打开结果
          </span>
        </footer>
      </section>
    </div>
  );
}

export { App };
