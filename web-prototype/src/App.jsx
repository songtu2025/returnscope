import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import {
  Pulse,
  ArrowRight,
  CaretRight,
  CheckCircle,
  Clock,
  Database,
  ListChecks,
  LockKey,
  MagnifyingGlass,
  PlayCircle,
  ShieldCheck,
  SignOut,
  WarningCircle,
} from "@phosphor-icons/react";
import { ApiError, api } from "./api";
import { AppShell } from "./app/AppShell";
import { navigateHash, useHashRoute } from "./app/hashRouter";
import { PRIMARY_NAV_ITEMS, SETTINGS_NAV_ITEM } from "./app/navigation";
import { Toast } from "./components/SharedUi";
import { STATUS_LABELS } from "./constants";
import { classNames } from "./lib/presentation";
import { SESSION_EXPIRED_EVENT } from "./shared/api/request";

const WorkbenchPage = lazy(() =>
  import("./features/workbench/WorkbenchPage").then((module) => ({
    default: module.WorkbenchPage,
  })),
);
const TaskCreatePage = lazy(() =>
  import("./features/task-create/TaskCreatePage").then((module) => ({
    default: module.TaskCreatePage,
  })),
);
const TaskRuntimePage = lazy(() =>
  import("./features/task-runtime/TaskRuntimePage").then((module) => ({
    default: module.TaskRuntimePage,
  })),
);
const ReviewCenter = lazy(() =>
  import("./pages/ReviewCenter").then((module) => ({
    default: module.ReviewCenter,
  })),
);
const DataAssetsPage = lazy(() =>
  import("./features/data-management/DataAssetsPage").then((module) => ({
    default: module.DataAssetsPage,
  })),
);
const ResultsPage = lazy(() =>
  import("./pages/ResultsPage").then((module) => ({ default: module.ResultsPage })),
);
const ClassificationResultsPage = lazy(() =>
  import("./pages/ClassificationResultsPage").then((module) => ({
    default: module.ClassificationResultsPage,
  })),
);
const AnalysisDashboardPage = lazy(() =>
  import("./features/analysis-dashboards/AnalysisDashboardPage").then((module) => ({
    default: module.AnalysisDashboardPage,
  })),
);
const SystemSettingsPage = lazy(() =>
  import("./features/system-settings/SystemSettingsPage").then((module) => ({
    default: module.SystemSettingsPage,
  })),
);

function App() {
  const [user, setUser] = useState(null);
  const [booting, setBooting] = useState(true);
  const [system, setSystem] = useState(null);
  const [toast, setToast] = useState(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const { route, navigate } = useHashRoute();

  const notify = useCallback((message, tone = "success") => {
    setToast({ message, tone });
    window.setTimeout(() => setToast(null), 3200);
  }, []);

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
    const handleShortcut = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (user) setSearchOpen(true);
      }
      if (event.key === "Escape") setSearchOpen(false);
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, [user]);

  if (booting) return <LoadingScreen />;
  if (!user) {
    return (
      <LoginPage
        onLogin={(value) => {
          setUser(value);
          refreshSystem();
        }}
      />
    );
  }

  const page = route.page;
  return (
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
        system?.warnings?.length > 0 ? (
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
          <GlobalSearch
            open={searchOpen}
            onClose={() => setSearchOpen(false)}
            onSelect={(destination, focus) => {
              setSearchOpen(false);
              navigate(destination, focus);
            }}
            notify={notify}
          />
          {toast && <Toast {...toast} />}
        </>
      }
    >
      <Suspense fallback={<div className="empty-state">正在加载页面…</div>}>
        {page === "workbench" && (
          <WorkbenchPage system={system} onNavigate={navigate} />
        )}
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
        {page === "legacy-results" && (
          <Suspense fallback={<div className="empty-state">正在加载旧版任务分析…</div>}>
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
          <Suspense fallback={<div className="empty-state">正在加载分类结果池…</div>}>
            <ClassificationResultsPage notify={notify} route={route} userId={user.id} />
          </Suspense>
        )}
        {page === "analysis-dashboards" && (
          <AnalysisDashboardPage
            route={route}
            onNavigate={navigate}
            notify={notify}
            userId={user.id}
          />
        )}
        {page === "settings" && (
          <SystemSettingsPage route={route} notify={notify} currentUser={user} />
        )}
      </Suspense>
    </AppShell>
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

function LoginPage({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      onLogin(await api.login(email, password));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-page">
      <section className="login-story">
        <div className="brand-lockup">
          <img src="/assets/brand-mark.png" alt="" />
          <span>Seekway Intelligence</span>
        </div>
        <div>
          <p className="eyebrow light">退货语义分析智能体</p>
          <h1>
            让每一条退货评论
            <br />
            都进入可追踪的决策流程
          </h1>
          <p className="login-lead">
            数据版本、模型运行、人工复核与结果交付集中在一个工作台，所有修改都有留痕。
          </p>
        </div>
        <div className="login-proof">
          <span>
            <CheckCircle size={18} /> 后台持续运行
          </span>
          <span>
            <ShieldCheck size={18} /> 配置与数据快照
          </span>
          <span>
            <Clock size={18} /> 全流程修改留痕
          </span>
        </div>
      </section>
      <section className="login-panel">
        <form className="login-card" onSubmit={submit}>
          <div className="login-icon">
            <LockKey size={24} />
          </div>
          <p className="eyebrow">团队工作台</p>
          <h2>登录并继续分析</h2>
          <p>使用团队管理员为你创建的账号。</p>
          <label>
            邮箱
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label>
            密码
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
              autoFocus
            />
          </label>
          {error && (
            <div className="form-error">
              <WarningCircle size={17} />
              {error}
            </div>
          )}
          <button className="primary-button login-submit" disabled={submitting}>
            {submitting ? "正在登录…" : "进入工作台"}
            <ArrowRight size={18} />
          </button>
        </form>
      </section>
    </div>
  );
}

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
          <strong>退货语义分析</strong>
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
      <div className="sidebar-status">
        <div>
          <span
            className={classNames(
              "health-dot",
              system?.worker_status === "unavailable" && "offline",
            )}
          />
          <b>
            {!system
              ? "正在连接运行服务"
              : system.worker_status === "ok"
                ? "运行服务正常"
                : "后台执行器异常"}
          </b>
        </div>
        <p>后台 Listing 槽位 {system?.worker_concurrency ?? 15}</p>
        <small>Desktop Web · v1.0</small>
      </div>
    </aside>
  );
}

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
      aria-current={active ? "page" : undefined}
    >
      <Icon
        className="sidebar-nav-icon"
        size={20}
        weight={active ? "duotone" : "regular"}
        aria-hidden="true"
      />
      <span>{label}</span>
      {badge > 0 && <em>{badge > 99 ? "99+" : badge}</em>}
    </button>
  );
}

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

function GlobalSearch({ open, onClose, onSelect, notify }) {
  const [query, setQuery] = useState("");
  const [resources, setResources] = useState({
    tasks: [],
    datasets: [],
    reviews: [],
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setLoading(true);
    Promise.all([api.tasks(), api.datasets(), api.reviews()])
      .then(([tasks, datasets, reviews]) => setResources({ tasks, datasets, reviews }))
      .catch((error) => notify(error.message, "error"))
      .finally(() => setLoading(false));
  }, [open, notify]);

  if (!open) return null;
  const items = [
    ...resources.tasks.map((task) => ({
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
    })),
    ...resources.datasets
      .filter((dataset) => dataset.kind === "products")
      .map((dataset) => ({
        id: dataset.id,
        type: "产品信息",
        icon: Database,
        title: dataset.name,
        meta: `v${dataset.current_version} · ${dataset.row_count.toLocaleString()} 行`,
        keywords: `${dataset.name} ${dataset.description ?? ""} ${dataset.kind}`,
        page: "data-assets",
        focus: { kind: "dataset", id: dataset.id, datasetKind: dataset.kind },
      })),
    ...resources.reviews.map((review) => ({
      id: review.id,
      type: review.workflow_status === "pending" ? "待复核" : "已复核",
      icon: ListChecks,
      title: review.comment,
      meta: `${review.task_title} · ${review.owner_name}`,
      keywords: `${review.comment} ${review.task_title} ${review.owner_name}`,
      page: "review",
      focus: { kind: "review", id: review.id, status: review.workflow_status },
    })),
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
        className="command-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="全局搜索"
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
            autoFocus
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
export default App;
