import { useEffect, useState } from "react";
import { ArrowRight, ShieldCheck } from "@phosphor-icons/react";
import { api } from "../../api";
import { navigateHash } from "../../app/hashRouter";
import { InlineLoading } from "../../components/SharedUi";
import { InvalidLinkCard } from "./AuthUi";
import { FormError } from "./AuthUi";
import { errorMessage } from "../../shared/api/requestErrors";
import { PASSWORD_MIN_LENGTH } from "./authPresentation";

/** @typedef {import("./authPresentation").CurrentUser} CurrentUser */

/** @param {{token: string, onLogin: (user: CurrentUser) => void}} props */
export function RegisterPage({ token, onLogin }) {
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
