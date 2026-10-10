import { WarningCircle } from "@phosphor-icons/react";
import { navigateHash } from "../../app/hashRouter";

/** @param {{children: import("react").ReactNode}} props */
export function AuthShell({ children }) {
  return (
    <div className="login-page">
      <section className="login-story">
        <div className="brand-lockup">
          <img src="/assets/brand-mark-160.png" alt="" />
          <span>Seekway Intelligence</span>
        </div>
        <div className="login-story-content">
          <p className="eyebrow light">用户语义分析智能体</p>
          <h1>
            让每一条用户反馈
            <br />
            都进入可追踪的决策流程
          </h1>
        </div>
      </section>
      <section className="login-panel">{children}</section>
    </div>
  );
}

/** @param {{message: string}} props */
export function FormError({ message }) {
  if (!message) return null;
  return (
    <div className="form-error" role="alert">
      <WarningCircle size={17} />
      {message}
    </div>
  );
}

/** @param {{title: string, description: string, actionLabel?: string, actionPage?: string}} props */
export function InvalidLinkCard({
  title,
  description,
  actionLabel = "返回登录",
  actionPage = "login",
}) {
  return (
    <section className="login-card auth-result-card" role="alert">
      <div className="login-icon auth-warning-icon">
        <WarningCircle size={24} />
      </div>
      <p className="eyebrow">链接验证</p>
      <h2>{title}</h2>
      <p>{description}</p>
      <button
        className="secondary-button auth-full-button"
        onClick={() => navigateHash(actionPage)}
      >
        {actionLabel}
      </button>
    </section>
  );
}
