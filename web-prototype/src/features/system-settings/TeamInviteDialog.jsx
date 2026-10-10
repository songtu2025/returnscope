import { Modal } from "../../components/SharedUi";

/** @param {{setShowInviteModal: (open: boolean) => void, submit: (event: import("react").FormEvent<HTMLFormElement>) => Promise<void>, inviteEmail: string, setInviteEmail: (email: string) => void, inviting: boolean}} props */
export function TeamInviteDialog({
  setShowInviteModal,
  submit,
  inviteEmail,
  setInviteEmail,
  inviting,
}) {
  const inviteHint = /^\S+@\S+\.\S+$/.test(inviteEmail) ? "" : "请填写有效邮箱。";
  return (
    <Modal
      eyebrow="团队邀请"
      title="邀请用户"
      onClose={() => setShowInviteModal(false)}
    >
      <form className="modal-form invite-card" onSubmit={submit}>
        <label>
          邮箱
          <input
            aria-label="邮箱"
            type="email"
            value={inviteEmail}
            onChange={(event) => setInviteEmail(event.target.value)}
            required
            autoFocus
          />
          <small>成员将通过邮件中的一次性链接设置姓名和密码。</small>
        </label>
        <div className="modal-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={() => setShowInviteModal(false)}
          >
            取消
          </button>
          <button className="primary-button" disabled={inviting || Boolean(inviteHint)}>
            {inviting ? "正在发送…" : "发送邀请"}
          </button>
        </div>
        {inviteHint && (
          <small role="status" aria-live="polite">
            {inviteHint}
          </small>
        )}
      </form>
    </Modal>
  );
}
