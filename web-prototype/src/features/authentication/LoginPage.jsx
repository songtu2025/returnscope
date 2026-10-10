import { useState } from "react";
import { ArrowRight, CheckCircle } from "@phosphor-icons/react";
import { api } from "../../api";
import { navigateHash } from "../../app/hashRouter";
import { FormError } from "./AuthUi";
import { errorMessage } from "../../shared/api/requestErrors";

/** @typedef {import("./authPresentation").CurrentUser} CurrentUser */

/** @param {{onLogin: (user: CurrentUser) => void, notice?: string}} props */
export function LoginPage({ onLogin, notice = "" }) {
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
      <h2>登录</h2>
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
