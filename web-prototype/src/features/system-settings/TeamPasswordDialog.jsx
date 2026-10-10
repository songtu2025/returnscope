import { Modal } from "../../components/SharedUi";
import { PASSWORD_MIN_LENGTH } from "../authentication/authPresentation";
/** @typedef {{current_password: string, new_password: string}} PasswordForm */

/** @param {PasswordForm} form */
function passwordHint(form) {
  if (!form.current_password) return "请填写当前密码。";
  if (form.new_password.length < PASSWORD_MIN_LENGTH) return "新密码至少 12 位。";
  return "";
}

/** @param {{setShowPasswordModal: (open: boolean) => void, changePassword: (event: import("react").FormEvent<HTMLFormElement>) => Promise<void>, passwordInputRef: import("react").RefObject<HTMLInputElement | null>, passwordForm: PasswordForm, setPasswordForm: (form: PasswordForm) => void, changingPassword: boolean}} props */
export function TeamPasswordDialog({
  setShowPasswordModal,
  changePassword,
  passwordInputRef,
  passwordForm,
  setPasswordForm,
  changingPassword,
}) {
  const passwordFormHint = passwordHint(passwordForm);
  return (
    <Modal
      eyebrow="账号安全"
      title="修改我的密码"
      onClose={() => setShowPasswordModal(false)}
    >
      <form className="modal-form invite-card" onSubmit={changePassword}>
        <label>
          当前密码
          <input
            ref={passwordInputRef}
            type="password"
            value={passwordForm.current_password}
            onChange={(event) =>
              setPasswordForm({
                ...passwordForm,
                current_password: event.target.value,
              })
            }
            required
            autoFocus
          />
        </label>
        <label>
          新密码
          <input
            type="password"
            minLength={PASSWORD_MIN_LENGTH}
            value={passwordForm.new_password}
            onChange={(event) =>
              setPasswordForm({
                ...passwordForm,
                new_password: event.target.value,
              })
            }
            required
          />
          <small>密码至少 12 位。修改成功后需要重新登录。</small>
        </label>
        <div className="modal-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={() => setShowPasswordModal(false)}
          >
            取消
          </button>
          <button
            className="primary-button"
            disabled={changingPassword || Boolean(passwordFormHint)}
          >
            {changingPassword ? "正在更新…" : "保存并重新登录"}
          </button>
        </div>
        {passwordFormHint && (
          <small role="status" aria-live="polite">
            {passwordFormHint}
          </small>
        )}
      </form>
    </Modal>
  );
}
