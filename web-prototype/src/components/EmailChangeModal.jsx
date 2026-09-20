import { useState } from "react";
import { EnvelopeSimple, WarningCircle } from "@phosphor-icons/react";

import { api } from "../api";
import { Modal } from "./SharedUi";

const EMAIL_PATTERN = /^\S+@\S+\.\S+$/;

/** @param {unknown} error */
function errorMessage(error) {
  return error instanceof Error ? error.message : "请求失败";
}

/**
 * @param {{currentEmail: string, onClose: () => void, notify: (message: string, tone?: string) => void}} props
 */
export function EmailChangeModal({ currentEmail, onClose, notify }) {
  const [newEmail, setNewEmail] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sentEmail, setSentEmail] = useState("");
  const [error, setError] = useState("");
  const normalizedEmail = newEmail.trim().toLowerCase();
  const formHint = !EMAIL_PATTERN.test(normalizedEmail)
    ? "请填写有效的新邮箱。"
    : normalizedEmail === currentEmail.toLowerCase()
      ? "新邮箱不能与当前邮箱相同。"
      : !currentPassword
        ? "请填写当前密码。"
        : "";

  const submit = async (/** @type {import("react").FormEvent} */ event) => {
    event.preventDefault();
    if (formHint) return;
    setSubmitting(true);
    setError("");
    try {
      await api.requestEmailChange({
        current_password: currentPassword,
        new_email: normalizedEmail,
      });
      setSentEmail(normalizedEmail);
      notify("验证邮件已发送");
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSubmitting(false);
    }
  };

  if (sentEmail) {
    return (
      <Modal eyebrow="账号安全" title="验证新邮箱" onClose={onClose}>
        <div className="modal-form invite-card auth-result-card">
          <div className="login-icon">
            <EnvelopeSimple size={24} />
          </div>
          <p role="status">
            验证邮件已发送至 <b>{sentEmail}</b>。完成验证前，仍使用 {currentEmail}
            登录。
          </p>
          <div className="modal-actions">
            <button type="button" className="primary-button" onClick={onClose}>
              我知道了
            </button>
          </div>
        </div>
      </Modal>
    );
  }

  return (
    <Modal eyebrow="账号安全" title="修改我的邮箱" onClose={onClose}>
      <form className="modal-form invite-card" onSubmit={submit}>
        <label>
          当前邮箱
          <input value={currentEmail} readOnly aria-readonly="true" />
        </label>
        <label>
          新邮箱
          <input
            aria-label="新邮箱"
            type="email"
            value={newEmail}
            onChange={(event) => setNewEmail(event.target.value)}
            autoComplete="email"
            required
            autoFocus
          />
          <small>系统会向新邮箱发送一次性验证链接。</small>
        </label>
        <label>
          当前密码
          <input
            aria-label="邮箱修改当前密码"
            type="password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        {error && (
          <div className="form-error" role="alert">
            <WarningCircle size={17} />
            {error}
          </div>
        )}
        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            取消
          </button>
          <button className="primary-button" disabled={submitting || Boolean(formHint)}>
            {submitting ? "正在发送…" : "发送验证邮件"}
          </button>
        </div>
        {formHint && (
          <small role="status" aria-live="polite">
            {formHint}
          </small>
        )}
      </form>
    </Modal>
  );
}
