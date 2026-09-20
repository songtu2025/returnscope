import { useCallback, useEffect, useRef, useState } from "react";
import { Power, UserPlus, WarningCircle } from "@phosphor-icons/react";
import { api } from "../api";
import { navigateHash } from "../app/hashRouter";
import {
  CardHeading,
  EmptyState,
  InlineLoading,
  Modal,
  PageHeading,
} from "../components/SharedUi";
import { classNames, formatTime } from "../lib/presentation";

/** @typedef {import("../shared/api/systemSettingsContracts").TeamUser} TeamUser */
/** @typedef {import("../shared/api/systemSettingsContracts").TeamInvitation} TeamInvitation */
/** @typedef {{current_password: string, new_password: string}} PasswordForm */
/** @typedef {Error & {status?: number}} TeamRequestError */

/** @param {unknown} error @returns {TeamRequestError} */
function requestError(error) {
  return error instanceof Error
    ? /** @type {TeamRequestError} */ (error)
    : new Error("请求失败");
}

/** @param {PasswordForm} form */
function passwordHint(form) {
  if (!form.current_password) return "请填写当前密码。";
  if (form.new_password.length < 12) return "新密码至少 12 位。";
  return "";
}

/** @param {{notify: (message: string, tone?: string) => void, currentUser?: {id?: string, display_name?: string, email?: string, is_admin?: boolean} | null, focusPassword?: boolean, focusUserId?: string | null}} props */
export function TeamPage({
  notify,
  currentUser,
  focusPassword = false,
  focusUserId = null,
}) {
  const [users, setUsers] = useState(/** @type {TeamUser[]} */ ([]));
  const [invitations, setInvitations] = useState(/** @type {TeamInvitation[]} */ ([]));
  const [loadState, setLoadState] = useState(
    /** @type {"loading" | "ready" | "error"} */ ("loading"),
  );
  const [loadError, setLoadError] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [passwordForm, setPasswordForm] = useState({
    current_password: "",
    new_password: "",
  });
  const [inviting, setInviting] = useState(false);
  const [invitationAction, setInvitationAction] = useState("");
  const [changingPassword, setChangingPassword] = useState(false);
  const [statusTarget, setStatusTarget] = useState(
    /** @type {TeamUser | null} */ (null),
  );
  const [statusNote, setStatusNote] = useState("");
  const [statusUpdating, setStatusUpdating] = useState(false);
  const passwordInputRef = useRef(/** @type {HTMLInputElement | null} */ (null));
  const focusedUserRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const hasLoadedUsers = useRef(false);
  const load = useCallback(async () => {
    const isInitialLoad = !hasLoadedUsers.current;
    if (isInitialLoad) {
      setLoadState("loading");
      setLoadError("");
    }
    try {
      const [userValues, invitationValues] = await Promise.all([
        api.users(),
        api.invitations(),
      ]);
      setUsers(userValues);
      setInvitations(invitationValues);
      hasLoadedUsers.current = true;
      setLoadState("ready");
      setLoadError("");
    } catch (error) {
      if (isInitialLoad) {
        setLoadState("error");
        setLoadError(requestError(error).message);
      }
      throw error;
    }
  }, []);
  useEffect(() => {
    load().catch((error) => notify(error.message, "error"));
  }, [load, notify]);
  useEffect(() => {
    if (focusPassword) setShowPasswordModal(true);
  }, [focusPassword]);
  useEffect(() => {
    if (!focusPassword || !showPasswordModal) return;
    passwordInputRef.current?.scrollIntoView({ block: "center" });
    passwordInputRef.current?.focus();
  }, [focusPassword, showPasswordModal]);
  useEffect(() => {
    if (!focusUserId || !focusedUserRef.current) return;
    focusedUserRef.current.scrollIntoView?.({ block: "center" });
  }, [focusUserId, users]);
  const activeCount = users.filter((user) => Boolean(user.active)).length;
  const seatCount = activeCount + invitations.length;
  const currentAccount = users.find(
    (user) => String(user.id) === String(currentUser?.id),
  );
  const currentDisplayName =
    currentAccount?.display_name || currentUser?.display_name || "当前账号";
  const currentEmail = currentAccount?.email || currentUser?.email || "未提供邮箱";
  const inviteHint = /^\S+@\S+\.\S+$/.test(inviteEmail) ? "" : "请填写有效邮箱。";
  const passwordFormHint = passwordHint(passwordForm);
  /** @param {import("react").FormEvent<HTMLFormElement>} event */
  const submit = async (event) => {
    event.preventDefault();
    setInviting(true);
    try {
      await api.inviteUser({ email: inviteEmail });
      setInviteEmail("");
      setShowInviteModal(false);
      await load();
      notify("邀请邮件已发送");
    } catch (error) {
      notify(requestError(error).message, "error");
    } finally {
      setInviting(false);
    }
  };
  /** @param {string} invitationId @param {"resend" | "revoke"} action */
  const handleInvitation = async (invitationId, action) => {
    setInvitationAction(`${action}:${invitationId}`);
    try {
      if (action === "resend") {
        await api.resendInvitation(invitationId);
        notify("邀请邮件已重新发送");
      } else {
        await api.revokeInvitation(invitationId);
        notify("邀请已撤销");
      }
      await load();
    } catch (error) {
      notify(requestError(error).message, "error");
    } finally {
      setInvitationAction("");
    }
  };
  /** @param {import("react").FormEvent<HTMLFormElement>} event */
  const changePassword = async (event) => {
    event.preventDefault();
    setChangingPassword(true);
    try {
      await api.changePassword(passwordForm);
      notify("密码已更新，请重新登录");
      window.setTimeout(() => window.location.reload(), 800);
    } catch (error) {
      notify(requestError(error).message, "error");
    } finally {
      setChangingPassword(false);
    }
  };
  const updateStatus = async () => {
    if (!statusTarget) return;
    setStatusUpdating(true);
    try {
      await api.updateUserStatus(statusTarget.id, {
        active: !statusTarget.active,
        expected_active: Boolean(statusTarget.active),
        note: statusNote,
      });
      notify(statusTarget.active ? "团队账号已停用" : "团队账号已恢复");
      setStatusTarget(null);
      setStatusNote("");
      await load();
    } catch (error) {
      const nextError = requestError(error);
      if (nextError.status === 409) {
        await load();
        setStatusTarget(null);
        setStatusNote("");
      }
      notify(nextError.message, "error");
    } finally {
      setStatusUpdating(false);
    }
  };
  return (
    <div className="standard-page team-page">
      <PageHeading
        eyebrow="账号管理"
        title="用户与安全"
        description="管理可登录账号与当前账号密码。"
      />
      {loadState === "loading" && <InlineLoading label="正在读取用户与安全设置…" />}
      {loadState === "error" && (
        <section role="alert">
          <EmptyState
            icon={WarningCircle}
            title="用户与安全设置读取失败"
            description={loadError}
            action={
              <button
                type="button"
                className="secondary-button"
                onClick={() =>
                  load().catch((error) => notify(requestError(error).message, "error"))
                }
              >
                重新加载
              </button>
            }
          />
        </section>
      )}
      {loadState === "ready" && (
        <div className="team-layout">
          <section className="content-card">
            <CardHeading
              title="用户账号"
              note={`${seatCount}/5 个席位 · ${activeCount} 个启用账号 · ${invitations.length} 个待注册`}
              action={
                <button
                  className="primary-button compact-button"
                  disabled={seatCount >= 5}
                  onClick={() => setShowInviteModal(true)}
                >
                  <UserPlus size={16} />
                  {seatCount >= 5 ? "已达 5 人上限" : "邀请用户"}
                </button>
              }
            />
            <div className="member-table">
              <div className="table-head">
                <span>用户</span>
                <span>邮箱</span>
                <span>状态</span>
                <span>操作</span>
              </div>
              {users.map((user) => {
                const isFocused = String(user.id) === String(focusUserId);
                const isCurrentUser = String(user.id) === String(currentUser?.id);
                return (
                  <div
                    key={user.id}
                    ref={isFocused ? focusedUserRef : null}
                    className={isFocused ? "is-targeted" : ""}
                    aria-current={isFocused ? "true" : undefined}
                  >
                    <span className="member-name">
                      <i>{user.display_name.slice(0, 1)}</i>
                      <b>
                        {user.display_name}
                        {user.id === currentUser?.id && <small>当前账号</small>}
                      </b>
                    </span>
                    <span>{user.email}</span>
                    <em className={user.active ? "online" : ""}>
                      {user.active ? "启用" : "停用"}
                    </em>
                    <div className="member-actions">
                      {isCurrentUser ? (
                        <button
                          className="member-toggle"
                          onClick={() => setShowPasswordModal(true)}
                        >
                          改密码
                        </button>
                      ) : (
                        <button
                          className={classNames(
                            "member-toggle",
                            user.active && "danger",
                          )}
                          onClick={() => {
                            setStatusTarget(user);
                            setStatusNote("");
                          }}
                        >
                          {user.active ? "停用" : "启用"}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
              {users.length === 0 && <div className="team-empty-row">暂无用户账号</div>}
            </div>
            <div className="pending-invitations">
              <div className="pending-invitations-heading">
                <div>
                  <b>待注册邀请</b>
                  <span>邀请在注册完成前占用一个团队席位。</span>
                </div>
                <em>{invitations.length} 个待处理</em>
              </div>
              <div className="invitation-table">
                <div className="table-head">
                  <span>邮箱</span>
                  <span>有效期至</span>
                  <span>状态</span>
                  <span>操作</span>
                </div>
                {invitations.map((invitation) => (
                  <div key={invitation.id}>
                    <span>{invitation.email}</span>
                    <span>{formatTime(invitation.expires_at)}</span>
                    <em>待注册</em>
                    <div className="member-actions invitation-actions">
                      <button
                        className="member-toggle"
                        disabled={Boolean(invitationAction)}
                        onClick={() => handleInvitation(invitation.id, "resend")}
                      >
                        {invitationAction === `resend:${invitation.id}`
                          ? "发送中…"
                          : "重新发送"}
                      </button>
                      <button
                        className="member-toggle danger"
                        disabled={Boolean(invitationAction)}
                        onClick={() => handleInvitation(invitation.id, "revoke")}
                      >
                        {invitationAction === `revoke:${invitation.id}`
                          ? "撤销中…"
                          : "撤销"}
                      </button>
                    </div>
                  </div>
                ))}
                {invitations.length === 0 && (
                  <div className="team-empty-row">暂无待注册邀请</div>
                )}
              </div>
            </div>
            <div className="team-security-bar" id="change-password">
              <div>
                <span>账号安全</span>
                <b>
                  当前登录账号：{currentDisplayName} · {currentEmail}
                </b>
                <small>关键操作会写入审计记录。</small>
              </div>
              <div className="team-security-actions">
                <button
                  className="secondary-button"
                  onClick={() => setShowPasswordModal(true)}
                >
                  修改我的密码
                </button>
                <button
                  className="secondary-button"
                  onClick={() => navigateHash("settings", { tab: "audit" })}
                >
                  查看审计记录
                </button>
              </div>
            </div>
          </section>
        </div>
      )}
      {showInviteModal && (
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
              <button
                className="primary-button"
                disabled={inviting || seatCount >= 5 || Boolean(inviteHint)}
              >
                {inviting ? "正在发送…" : "发送邀请"}
              </button>
            </div>
            {seatCount < 5 && inviteHint && (
              <small role="status" aria-live="polite">
                {inviteHint}
              </small>
            )}
          </form>
        </Modal>
      )}
      {showPasswordModal && (
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
                minLength={12}
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
      )}
      {statusTarget && (
        <Modal
          eyebrow="团队账号"
          title={`${statusTarget.active ? "停用" : "恢复"}${statusTarget.display_name}的账号`}
          onClose={() => {
            setStatusTarget(null);
            setStatusNote("");
          }}
        >
          <div className="modal-form account-status-confirm">
            <Power size={28} />
            <p>
              {statusTarget.active
                ? "停用后，该成员的全部登录会话会立即失效，但历史任务和修改记录仍会保留。"
                : "恢复后，该成员可以继续使用原邮箱和密码登录。"}
            </p>
            <label className="account-status-note">
              操作原因
              <textarea
                value={statusNote}
                onChange={(event) => setStatusNote(event.target.value)}
                maxLength={500}
                rows={3}
                placeholder="必填，说明停用或恢复原因"
                required
                autoFocus
              />
            </label>
            {statusTarget.audit?.some((item) =>
              ["activate", "deactivate"].includes(item.action),
            ) && (
              <div className="account-audit-list">
                <b>最近状态修改</b>
                {statusTarget.audit
                  .filter((item) => ["activate", "deactivate"].includes(item.action))
                  .slice(0, 3)
                  .map((item) => (
                    <div key={item.id}>
                      <span>
                        {item.before?.active ? "可使用" : "已停用"} →{" "}
                        {item.after?.active ? "可使用" : "已停用"}
                      </span>
                      <p>{item.after?.note}</p>
                      <small>
                        {item.actor_name} · {formatTime(item.created_at)}
                      </small>
                    </div>
                  ))}
              </div>
            )}
            <div className="modal-actions">
              <button
                className="secondary-button"
                onClick={() => {
                  setStatusTarget(null);
                  setStatusNote("");
                }}
              >
                取消
              </button>
              <button
                className={classNames(
                  "primary-button",
                  statusTarget.active && "danger-button",
                )}
                disabled={statusUpdating || !statusNote.trim()}
                onClick={updateStatus}
              >
                {statusUpdating ? "正在处理…" : "确认"}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
