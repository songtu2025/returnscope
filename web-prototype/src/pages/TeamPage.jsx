import { useCallback, useEffect, useRef, useState } from "react";
import { Power, UserPlus, WarningCircle } from "@phosphor-icons/react";
import { api } from "../api";
import {
  CardHeading,
  EmptyState,
  InlineLoading,
  Modal,
  PageHeading,
} from "../components/SharedUi";
import { EmailChangeModal } from "../components/EmailChangeModal";
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
  const [showEmailModal, setShowEmailModal] = useState(false);
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
  const focusedUserRef = useRef(/** @type {HTMLTableRowElement | null} */ (null));
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
  const currentAccount = users.find(
    (user) => String(user.id) === String(currentUser?.id),
  );
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
    <div className="standard-page narrow-page team-page">
      <PageHeading
        eyebrow="账号管理"
        title="用户与安全"
        description="管理团队账号、邀请与当前账号凭据。"
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
          <section className="content-card access-console">
            <CardHeading
              title="访问控制台"
              note={`${activeCount} 个启用账号 · ${invitations.length} 个待注册`}
              action={
                <button
                  type="button"
                  className="primary-button compact-button"
                  onClick={() => setShowInviteModal(true)}
                >
                  <UserPlus size={16} />
                  邀请用户
                </button>
              }
            />
            <section className="access-section" aria-labelledby="member-list-title">
              <div className="access-section-heading">
                <h3 id="member-list-title">团队成员</h3>
                <span>{users.length} 个账号</span>
              </div>
              <div className="access-table-scroll">
                <table className="member-table" aria-label="团队成员">
                  <thead>
                    <tr>
                      <th scope="col">用户</th>
                      <th scope="col">邮箱</th>
                      <th scope="col">状态</th>
                      <th scope="col">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((user) => {
                      const isFocused = String(user.id) === String(focusUserId);
                      const isCurrentUser = String(user.id) === String(currentUser?.id);
                      return (
                        <tr
                          key={user.id}
                          ref={isFocused ? focusedUserRef : null}
                          className={classNames(
                            isCurrentUser && "current-account",
                            isFocused && "is-targeted",
                          )}
                          aria-current={isFocused ? "true" : undefined}
                        >
                          <td>
                            <span className="member-name">
                              <i>{user.display_name.slice(0, 1)}</i>
                              <b>
                                {user.display_name}
                                {isCurrentUser && <small>当前账号</small>}
                              </b>
                            </span>
                          </td>
                          <td>{user.email}</td>
                          <td>
                            <em className={user.active ? "online" : ""}>
                              {user.active ? "启用" : "停用"}
                            </em>
                          </td>
                          <td>
                            <div className="member-actions">
                              {isCurrentUser ? (
                                <>
                                  <button
                                    type="button"
                                    className="member-toggle"
                                    onClick={() => setShowEmailModal(true)}
                                  >
                                    修改邮箱
                                  </button>
                                  <button
                                    type="button"
                                    className="member-toggle"
                                    onClick={() => setShowPasswordModal(true)}
                                  >
                                    修改密码
                                  </button>
                                </>
                              ) : (
                                <button
                                  type="button"
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
                          </td>
                        </tr>
                      );
                    })}
                    {users.length === 0 && (
                      <tr className="team-empty-row">
                        <td colSpan={4}>暂无用户账号</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>
            <section
              className="access-section pending-invitations"
              aria-labelledby="pending-invitations-title"
            >
              <div className="access-section-heading">
                <div>
                  <h3 id="pending-invitations-title">待注册邀请</h3>
                  <p>等待成员通过邮件完成注册。</p>
                </div>
                <span>{invitations.length} 个待处理</span>
              </div>
              <div className="access-table-scroll">
                <table className="invitation-table" aria-label="待注册邀请">
                  <thead>
                    <tr>
                      <th scope="col">邮箱</th>
                      <th scope="col">有效期至</th>
                      <th scope="col">状态</th>
                      <th scope="col">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {invitations.map((invitation) => (
                      <tr key={invitation.id}>
                        <td>{invitation.email}</td>
                        <td>{formatTime(invitation.expires_at)}</td>
                        <td>
                          <em>待注册</em>
                        </td>
                        <td>
                          <div className="member-actions invitation-actions">
                            <button
                              type="button"
                              className="member-toggle"
                              disabled={Boolean(invitationAction)}
                              onClick={() => handleInvitation(invitation.id, "resend")}
                            >
                              {invitationAction === `resend:${invitation.id}`
                                ? "发送中…"
                                : "重新发送"}
                            </button>
                            <button
                              type="button"
                              className="member-toggle danger"
                              disabled={Boolean(invitationAction)}
                              onClick={() => handleInvitation(invitation.id, "revoke")}
                            >
                              {invitationAction === `revoke:${invitation.id}`
                                ? "撤销中…"
                                : "撤销"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {invitations.length === 0 && (
                      <tr className="team-empty-row">
                        <td colSpan={4}>暂无待注册邀请</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>
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
                disabled={inviting || Boolean(inviteHint)}
              >
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
      )}
      {showEmailModal && (
        <EmailChangeModal
          currentEmail={currentEmail}
          notify={notify}
          onClose={() => setShowEmailModal(false)}
        />
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
