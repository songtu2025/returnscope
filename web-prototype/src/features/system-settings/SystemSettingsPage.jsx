import { ApiManagement } from "../../pages/ApiManagement";
import { TeamPage } from "../../pages/TeamPage";
import { navigateHash } from "../../app/hashRouter";
import { AuditLogPage } from "./AuditLogPage";
import { ModelPreferencePage } from "./ModelPreferencePage";

export function SystemSettingsPage({ route, notify, currentUser }) {
  const requestedTab = route.query.tab;
  const isAdmin = currentUser?.is_admin === true;
  const tab =
    ["api", "models", "service"].includes(requestedTab) && isAdmin
      ? "service"
      : ["users", "audit"].includes(requestedTab) && isAdmin
        ? requestedTab
        : requestedTab === "model-preference"
          ? "model-preference"
          : isAdmin
            ? "service"
            : "model-preference";
  return (
    <>
      <div className="standard-page settings-hub-page">
        <div className="data-tabs settings-tabs" aria-label="系统设置分类">
          <button
            className={tab === "model-preference" ? "active" : ""}
            aria-current={tab === "model-preference" ? "page" : undefined}
            onClick={() => navigateHash("settings", { tab: "model-preference" })}
          >
            我的模型偏好
          </button>
          {isAdmin && (
            <>
              <button
                className={tab === "service" ? "active" : ""}
                aria-current={tab === "service" ? "page" : undefined}
                onClick={() => navigateHash("settings", { tab: "service" })}
              >
                模型服务
              </button>
              <button
                className={tab === "users" ? "active" : ""}
                aria-current={tab === "users" ? "page" : undefined}
                onClick={() => navigateHash("settings", { tab: "users" })}
              >
                用户与安全
              </button>
              <button
                className={tab === "audit" ? "active" : ""}
                aria-current={tab === "audit" ? "page" : undefined}
                onClick={() => navigateHash("settings", { tab: "audit" })}
              >
                审计记录
              </button>
            </>
          )}
        </div>
      </div>
      {tab === "model-preference" ? (
        <ModelPreferencePage notify={notify} />
      ) : tab === "service" ? (
        <ApiManagement
          notify={notify}
          focusConnectionId={route.query.connection_id || null}
          focusConfigVersionId={route.query.config_version_id || null}
          focusModelId={route.query.model_id || null}
        />
      ) : tab === "audit" ? (
        <AuditLogPage route={route} />
      ) : (
        <TeamPage
          notify={notify}
          currentUser={currentUser}
          focusPassword={route.query.action === "password"}
          focusUserId={route.query.user_id || null}
        />
      )}
    </>
  );
}
