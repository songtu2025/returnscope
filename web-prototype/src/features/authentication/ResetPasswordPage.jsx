import { useEffect, useState } from "react";
import { ArrowRight, Key } from "@phosphor-icons/react";
import { api } from "../../api";
import { navigateHash } from "../../app/hashRouter";
import { InlineLoading } from "../../components/SharedUi";
import { InvalidLinkCard } from "./AuthUi";
import { FormError } from "./AuthUi";
import { errorMessage } from "../../shared/api/requestErrors";
import { PASSWORD_MIN_LENGTH } from "./authPresentation";

/** @param {{token: string}} props */
export function ResetPasswordPage({ token }) {
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
