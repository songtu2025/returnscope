import { useState } from "react";
import { ArrowLeft, ArrowRight, EnvelopeSimple } from "@phosphor-icons/react";
import { api } from "../../api";
import { navigateHash } from "../../app/hashRouter";
import { FormError } from "./AuthUi";
import { errorMessage } from "../../shared/api/requestErrors";

export function ForgotPasswordPage() {
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
