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

export { App, Sidebar, Topbar };
