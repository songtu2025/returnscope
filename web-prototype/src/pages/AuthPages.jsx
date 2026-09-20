import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  Clock,
  EnvelopeSimple,
  Key,
  LockKey,
  ShieldCheck,
  WarningCircle,
} from "@phosphor-icons/react";

import { api } from "../api";
import { navigateHash } from "../app/hashRouter";
import { InlineLoading } from "../components/SharedUi";

const PASSWORD_MIN_LENGTH = 12;

/** @typedef {{id: string, email: string, display_name: string, is_admin?: boolean}} CurrentUser */
/** @typedef {{page: string, query: Record<string, string | undefined>}} AuthRoute */

/** @param {unknown} error */
function errorMessage(error) {
  return error instanceof Error ? error.message : "请求失败";
}

/** @param {string} email */
function maskedEmail(email) {
  const [local = "", domain = ""] = email.split("@");
  const visible = local.slice(0, Math.min(2, local.length));
  return `${visible}${"*".repeat(Math.max(3, local.length - visible.length))}@${domain}`;
}

/** @param {{children: import("react").ReactNode}} props */
function AuthShell({ children }) {
  return (
    <div className="login-page">
      <section className="login-story">
        <div className="brand-lockup">
          <img src="/assets/brand-mark.png" alt="" />
          <span>Seekway Intelligence</span>
        </div>
        <div>
          <p className="eyebrow light">用户语义分析智能体</p>
          <h1>
            让每一条用户反馈
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
      <section className="login-panel">{children}</section>
    </div>
  );
}

/** @param {{message: string}} props */
function FormError({ message }) {
  if (!message) return null;
  return (
    <div className="form-error" role="alert">
      <WarningCircle size={17} />
      {message}
    </div>
  );
}

/** @param {{onLogin: (user: CurrentUser) => void, notice?: string}} props */
function LoginPage({ onLogin, notice = "" }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (/** @type {import("react").FormEvent} */ event) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      onLogin(await api.login(email, password));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="login-card" onSubmit={submit}>
      <div className="login-icon">
        <LockKey size={24} />
      </div>
      <p className="eyebrow">团队工作台</p>
      <h2>登录并继续分析</h2>
      <p>使用团队管理员邀请你注册的账号。</p>
      {notice && (
        <div className="auth-success" role="status">
          <CheckCircle size={17} />
          {notice}
        </div>
      )}
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
          aria-label="密码"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="current-password"
          required
          autoFocus
        />
      </label>
      <button
        type="button"
        className="auth-text-action"
        onClick={() => navigateHash("forgot-password")}
      >
        忘记密码？
      </button>
      <FormError message={error} />
      <button className="primary-button login-submit" disabled={submitting}>
        {submitting ? "正在登录…" : "进入工作台"}
        <ArrowRight size={18} />
      </button>
    </form>
  );
}

function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  const submit = async (/** @type {import("react").FormEvent} */ event) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await api.requestPasswordReset(email);
      setSent(true);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSubmitting(false);
    }
  };

  if (sent) {
    return (
      <section className="login-card auth-result-card" aria-labelledby="reset-sent">
        <div className="login-icon">
          <EnvelopeSimple size={24} />
        </div>
        <p className="eyebrow">密码重置</p>
        <h2 id="reset-sent">请检查邮箱</h2>
        <p>如果该邮箱对应可用账号，我们已发送重置链接。请在 30 分钟内完成操作。</p>
        <button
          className="secondary-button auth-full-button"
          onClick={() => navigateHash("login")}
        >
          <ArrowLeft size={17} />
          返回登录
        </button>
      </section>
    );
  }

  return (
    <form className="login-card" onSubmit={submit}>
      <div className="login-icon">
        <EnvelopeSimple size={24} />
      </div>
      <p className="eyebrow">密码重置</p>
      <h2>找回密码</h2>
      <p>填写登录邮箱，我们会发送一次性重置链接。</p>
      <label>
        邮箱
        <input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          autoComplete="email"
          required
          autoFocus
        />
      </label>
      <FormError message={error} />
      <button className="primary-button login-submit" disabled={submitting}>
        {submitting ? "正在发送…" : "发送重置链接"}
        <ArrowRight size={18} />
      </button>
      <button
        type="button"
        className="auth-back-action"
        onClick={() => navigateHash("login")}
      >
        <ArrowLeft size={16} />
        返回登录
      </button>
    </form>
  );
}

/** @param {{token: string, onLogin: (user: CurrentUser) => void}} props */
function RegisterPage({ token, onLogin }) {
  const [state, setState] = useState(
    /** @type {"loading" | "valid" | "invalid"} */ ("loading"),
  );
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let active = true;
    if (!token) {
      setState("invalid");
      return () => {
        active = false;
      };
    }
    api
      .validateInvitation(token)
      .then((result) => {
        if (!active) return;
        setEmail(result.email);
        setState("valid");
      })
      .catch(() => active && setState("invalid"));
    return () => {
      active = false;
    };
  }, [token]);

  const formHint = !displayName.trim()
    ? "请填写姓名。"
    : password.length < PASSWORD_MIN_LENGTH
      ? `密码至少 ${PASSWORD_MIN_LENGTH} 位。`
      : password !== confirmation
        ? "两次输入的密码不一致。"
        : "";

  const submit = async (/** @type {import("react").FormEvent} */ event) => {
    event.preventDefault();
    if (formHint) return;
    setSubmitting(true);
    setError("");
    try {
      const user = await api.register({
        token,
        display_name: displayName.trim(),
        password,
      });
      navigateHash("workbench", {}, { replace: true });
      onLogin(user);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSubmitting(false);
    }
  };

  if (state === "loading") {
    return <InlineLoading label="正在验证邀请链接…" />;
  }
  if (state === "invalid") {
    return (
      <InvalidLinkCard
        title="邀请链接不可用"
        description="该邀请可能已过期、已使用或已被撤销，请联系管理员重新邀请。"
      />
    );
  }

  return (
    <form className="login-card auth-wide-card" onSubmit={submit}>
      <div className="login-icon">
        <ShieldCheck size={24} />
      </div>
      <p className="eyebrow">团队邀请</p>
      <h2>完成注册</h2>
      <p>设置姓名和密码后即可进入团队工作台。</p>
      <label>
        受邀邮箱
        <input value={email} readOnly aria-readonly="true" />
      </label>
      <label>
        姓名
        <input
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          autoComplete="name"
          maxLength={60}
          required
          autoFocus
        />
      </label>
      <label>
        密码
        <input
          aria-label="密码"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="new-password"
          minLength={PASSWORD_MIN_LENGTH}
          required
        />
        <small>至少 {PASSWORD_MIN_LENGTH} 位。</small>
      </label>
      <label>
        确认密码
        <input
          aria-label="确认密码"
          type="password"
          value={confirmation}
          onChange={(event) => setConfirmation(event.target.value)}
          autoComplete="new-password"
          minLength={PASSWORD_MIN_LENGTH}
          required
        />
      </label>
      <FormError message={error} />
      <button
        className="primary-button login-submit"
        disabled={submitting || Boolean(formHint)}
      >
        {submitting ? "正在注册…" : "注册并进入工作台"}
        <ArrowRight size={18} />
      </button>
      {formHint && (
        <small className="auth-form-hint" role="status" aria-live="polite">
          {formHint}
        </small>
      )}
    </form>
  );
}

/** @param {{token: string}} props */
function ResetPasswordPage({ token }) {
  const [state, setState] = useState(
    /** @type {"loading" | "valid" | "invalid"} */ ("loading"),
  );
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let active = true;
    if (!token) {
      setState("invalid");
      return () => {
        active = false;
      };
    }
    api
      .validatePasswordReset(token)
      .then(() => active && setState("valid"))
      .catch(() => active && setState("invalid"));
    return () => {
      active = false;
    };
  }, [token]);

  const formHint =
    password.length < PASSWORD_MIN_LENGTH
      ? `新密码至少 ${PASSWORD_MIN_LENGTH} 位。`
      : password !== confirmation
        ? "两次输入的密码不一致。"
        : "";

  const submit = async (/** @type {import("react").FormEvent} */ event) => {
    event.preventDefault();
    if (formHint) return;
    setSubmitting(true);
    setError("");
    try {
      await api.completePasswordReset({ token, new_password: password });
      navigateHash("login", { notice: "password-reset" }, { replace: true });
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSubmitting(false);
    }
  };

  if (state === "loading") {
    return <InlineLoading label="正在验证重置链接…" />;
  }
  if (state === "invalid") {
    return (
      <InvalidLinkCard
        title="重置链接不可用"
        description="该链接可能已过期或已使用，请重新申请密码重置。"
        actionLabel="重新申请"
        actionPage="forgot-password"
      />
    );
  }

  return (
    <form className="login-card" onSubmit={submit}>
      <div className="login-icon">
        <Key size={24} />
      </div>
      <p className="eyebrow">账号安全</p>
      <h2>设置新密码</h2>
      <p>更新后，其他设备上的登录会话会自动失效。</p>
      <label>
        新密码
        <input
          aria-label="新密码"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="new-password"
          minLength={PASSWORD_MIN_LENGTH}
          required
          autoFocus
        />
        <small>至少 {PASSWORD_MIN_LENGTH} 位。</small>
      </label>
      <label>
        确认新密码
        <input
          aria-label="确认新密码"
          type="password"
          value={confirmation}
          onChange={(event) => setConfirmation(event.target.value)}
          autoComplete="new-password"
          minLength={PASSWORD_MIN_LENGTH}
          required
        />
      </label>
      <FormError message={error} />
      <button
        className="primary-button login-submit"
        disabled={submitting || Boolean(formHint)}
      >
        {submitting ? "正在更新…" : "更新密码"}
        <ArrowRight size={18} />
      </button>
      {formHint && (
        <small className="auth-form-hint" role="status" aria-live="polite">
          {formHint}
        </small>
      )}
    </form>
  );
}

/** @param {{token: string, onSessionEnded: () => void}} props */
function ChangeEmailPage({ token, onSessionEnded }) {
  const [state, setState] = useState(
    /** @type {"loading" | "valid" | "invalid"} */ ("loading"),
  );
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let active = true;
    if (!token) {
      setState("invalid");
      return () => {
        active = false;
      };
    }
    api
      .validateEmailChange(token)
      .then((result) => {
        if (!active) return;
        setEmail(result.email);
        setState("valid");
      })
      .catch(() => active && setState("invalid"));
    return () => {
      active = false;
    };
  }, [token]);

  const complete = async () => {
    setSubmitting(true);
    setError("");
    try {
      await api.completeEmailChange(token);
      onSessionEnded();
      navigateHash("login", { notice: "email-changed" }, { replace: true });
    } catch (requestError) {
      setError(errorMessage(requestError));
      setSubmitting(false);
    }
  };

  if (state === "loading") {
    return <InlineLoading label="正在验证邮箱修改链接…" />;
  }
  if (state === "invalid") {
    return (
      <InvalidLinkCard
        title="邮箱验证链接不可用"
        description="该链接可能已过期、已使用或已被新请求替代。"
      />
    );
  }

  return (
    <section
      className="login-card auth-result-card"
      aria-labelledby="email-change-title"
    >
      <div className="login-icon">
        <EnvelopeSimple size={24} />
      </div>
      <p className="eyebrow">账号安全</p>
      <h2 id="email-change-title">确认修改登录邮箱</h2>
      <p>
        登录邮箱将修改为 <b>{maskedEmail(email)}</b>
        。完成后所有设备需要使用新邮箱重新登录。
      </p>
      <FormError message={error} />
      <button
        className="primary-button auth-full-button"
        disabled={submitting}
        onClick={complete}
      >
        {submitting ? "正在修改…" : "确认修改邮箱"}
      </button>
      <button
        type="button"
        className="auth-back-action"
        onClick={() => navigateHash("login")}
      >
        暂不修改
      </button>
    </section>
  );
}

/** @param {{title: string, description: string, actionLabel?: string, actionPage?: string}} props */
function InvalidLinkCard({
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

/** @param {{route: AuthRoute, onLogin: (user: CurrentUser) => void, onSessionEnded?: () => void}} props */
export function AuthPages({ route, onLogin, onSessionEnded = () => {} }) {
  let content;
  if (route.page === "forgot-password") {
    content = <ForgotPasswordPage />;
  } else if (route.page === "register") {
    content = <RegisterPage token={route.query.token ?? ""} onLogin={onLogin} />;
  } else if (route.page === "reset-password") {
    content = <ResetPasswordPage token={route.query.token ?? ""} />;
  } else if (route.page === "change-email") {
    content = (
      <ChangeEmailPage
        token={route.query.token ?? ""}
        onSessionEnded={onSessionEnded}
      />
    );
  } else {
    content = (
      <LoginPage
        onLogin={(user) => {
          if (route.page === "login") {
            navigateHash("workbench", {}, { replace: true });
          }
          onLogin(user);
        }}
        notice={
          route.query.notice === "password-reset"
            ? "密码已重置，请使用新密码登录。"
            : route.query.notice === "email-changed"
              ? "登录邮箱已更新，请使用新邮箱登录。"
              : ""
        }
      />
    );
  }
  return <AuthShell>{content}</AuthShell>;
}
