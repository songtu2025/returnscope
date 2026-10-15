import { useCallback, useEffect, useState } from "react";
import { SWRConfig } from "swr";
import { Pulse, ArrowRight, WarningCircle } from "@phosphor-icons/react";
import { ApiError, api } from "./api";
import { AppShell } from "./app/AppShell";
import { GlobalSearch } from "./app/GlobalSearch";
import { navigateHash, useHashRoute } from "./app/hashRouter";
import { Sidebar } from "./app/Sidebar";
import { Topbar } from "./app/Topbar";
import { AppPages } from "./app/AppPages";
import { Toast } from "./components/Toast";
import { SESSION_EXPIRED_EVENT } from "./shared/api/request";
import { serverStateConfig } from "./shared/serverState";
import { AuthPages } from "./pages/AuthPages";

const PUBLIC_AUTH_PAGES = new Set([
  "login",
  "forgot-password",
  "register",
  "reset-password",
  "change-email",
]);

/** @typedef {import("./app/appContracts").CurrentUser} CurrentUser */
/** @typedef {import("./app/appContracts").SystemStatus} SystemStatus */
/** @typedef {import("./app/appContracts").ToastState} ToastState */
/** @typedef {import("./app/appContracts").Notify} Notify */
function App() {
  const [user, setUser] = useState(/** @type {CurrentUser | null} */ (null));
  const [booting, setBooting] = useState(true);
  const [sessionError, setSessionError] = useState("");
  const [system, setSystem] = useState(/** @type {SystemStatus | null} */ (null));
  const [systemFailed, setSystemFailed] = useState(false);
  const [refreshingSystem, setRefreshingSystem] = useState(false);
  const [toast, setToast] = useState(/** @type {ToastState | null} */ (null));
  const [searchOpen, setSearchOpen] = useState(false);
  const { route, navigate } = useHashRoute();

  const notify = useCallback(
    /** @type {Notify} */
    (message, tone = "success") => {
      setToast({ message, tone });
    },
    [],
  );

  useEffect(() => {
    if (!toast || toast.tone === "error") return;
    const timer = window.setTimeout(() => setToast(null), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    const handleSessionExpired = () => {
      setUser(null);
      setSystem(null);
      setSessionError("");
      setSystemFailed(false);
      setSearchOpen(false);
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
    return () =>
      window.removeEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
  }, []);

  const refreshSystem = useCallback(async () => {
    setRefreshingSystem(true);
    try {
      setSystem(await api.status());
      setSystemFailed(false);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) setUser(null);
      else setSystemFailed(true);
    } finally {
      setRefreshingSystem(false);
    }
  }, []);

  const loadSession = useCallback(async () => {
    setBooting(true);
    setSessionError("");
    try {
      setUser(await api.me());
      void refreshSystem();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) setUser(null);
      else setSessionError("暂时无法确认登录状态，请重试连接。");
    } finally {
      setBooting(false);
    }
  }, [refreshSystem]);

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

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
  if (sessionError) return <LoadingScreen error={sessionError} onRetry={loadSession} />;
  if (!user || route.page === "change-email") {
    return (
      <AuthPages
        route={route}
        onLogin={(value) => {
          setUser(value);
          setSystem(null);
          setSystemFailed(false);
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
              setSystem(null);
              setSystemFailed(false);
            }}
          />
        }
        warning={
          <>
            {systemFailed && (
              <div className="system-warning" role="alert">
                <WarningCircle size={17} />
                <span>系统状态读取失败{system ? "，当前显示上次状态。" : "。"}</span>
                <button
                  className="secondary-button"
                  onClick={refreshSystem}
                  disabled={refreshingSystem}
                >
                  {refreshingSystem ? "重试中…" : "重试系统状态"}
                </button>
              </div>
            )}
            {system?.warnings && system.warnings.length > 0 ? (
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
            ) : null}
          </>
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
              />
            )}
            {toast && <Toast {...toast} onClose={() => setToast(null)} />}
          </>
        }
      >
        <AppPages
          route={route}
          user={user}
          notify={notify}
          navigate={navigate}
          refreshSystem={refreshSystem}
        />
      </AppShell>
    </SWRConfig>
  );
}

/** @param {{error?: string, onRetry?: () => void}} props */
function LoadingScreen({ error = "", onRetry } = {}) {
  return (
    <div className="loading-screen">
      <div className="brand-orb">
        {error ? <WarningCircle size={28} /> : <Pulse size={28} weight="bold" />}
      </div>
      <strong>{error ? "无法连接智能体工作台" : "正在连接智能体工作台"}</strong>
      <span role={error ? "alert" : undefined}>{error || "正在确认登录状态…"}</span>
      {error && (
        <button className="primary-button" onClick={onRetry}>
          重试连接
        </button>
      )}
    </div>
  );
}

export { App, Sidebar, Topbar };
