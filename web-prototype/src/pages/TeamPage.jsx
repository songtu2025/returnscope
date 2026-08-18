import { useCallback, useEffect, useRef, useState } from "react";
import { Power, UserPlus } from "@phosphor-icons/react";
import { api } from "../api";
import { navigateHash } from "../app/hashRouter";
import { CardHeading, Modal, PageHeading } from "../components/SharedUi";
import { classNames, formatTime } from "../lib/presentation";

function createAccountHint(form) {
  if (!form.display_name.trim()) return "请填写姓名。";
  if (!/^\S+@\S+\.\S+$/.test(form.email)) return "请填写有效邮箱。";
  if (form.password.length < 10) return "初始密码至少 10 位。";
  return "";
}

function passwordHint(form) {
  if (!form.current_password) return "请填写当前密码。";
  if (form.new_password.length < 10) return "新密码至少 10 位。";
  return "";
}

export function TeamPage({
  notify,
  currentUser,
  focusPassword = false,
  focusUserId = null,
}) {
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState({
    email: "",
    display_name: "",
    password: "",
  });
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [passwordForm, setPasswordForm] = useState({
    current_password: "",
    new_password: "",
  });
  const [adding, setAdding] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [statusTarget, setStatusTarget] = useState(null);
  const [statusNote, setStatusNote] = useState("");
  const [statusUpdating, setStatusUpdating] = useState(false);
  const passwordInputRef = useRef(null);
  const focusedUserRef = useRef(null);
  const load = useCallback(() => api.users().then(setUsers), []);
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
  const currentDisplayName =
    currentAccount?.display_name || currentUser?.display_name || "当前账号";
  const currentEmail = currentAccount?.email || currentUser?.email || "未提供邮箱";
  const accountHint = createAccountHint(form);
  const passwordFormHint = passwordHint(passwordForm);
  const submit = async (event) => {
    event.preventDefault();
    setAdding(true);
    try {
      await api.createUser(form);
      setForm({ email: "", display_name: "", password: "" });
      setShowCreateModal(false);
      await load();
      notify("团队账号已创建");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setAdding(false);
    }
  };
  const changePassword = async (event) => {
    event.preventDefault();
    setChangingPassword(true);
    try {
      await api.changePassword(passwordForm);
      notify("密码已更新，请重新登录");
      window.setTimeout(() => window.location.reload(), 800);
    } catch (error) {
      notify(error.message, "error");
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
      if (error.status === 409) {
        await load();
        setStatusTarget(null);
        setStatusNote("");
      }
      notify(error.message, "error");
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
      <div className="team-layout">
        <section className="content-card">
          <CardHeading
            title="用户账号"
            note={`${activeCount}/5 个启用账号 · ${users.length} 个账号`}
            action={
              <button
                className="primary-button compact-button"
                disabled={activeCount >= 5}
                onClick={() => setShowCreateModal(true)}
              >
                <UserPlus size={16} />
                {activeCount >= 5 ? "已达 5 人上限" : "新增用户"}
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
                      {user.id === currentUser.id && <small>当前账号</small>}
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
                        className={classNames("member-toggle", user.active && "danger")}
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
      {showCreateModal && (
        <Modal
          eyebrow="用户账号"
          title="新增用户"
          onClose={() => setShowCreateModal(false)}
        >
          <form className="modal-form invite-card" onSubmit={submit}>
            <label>
              姓名
              <input
                value={form.display_name}
                onChange={(event) =>
                  setForm({ ...form, display_name: event.target.value })
                }
                required
                autoFocus
              />
            </label>
            <label>
              邮箱
              <input
                type="email"
                value={form.email}
                onChange={(event) => setForm({ ...form, email: event.target.value })}
                required
              />
            </label>
            <label>
              初始密码
              <input
                type="password"
                minLength="10"
                value={form.password}
                onChange={(event) => setForm({ ...form, password: event.target.value })}
                required
              />
              <small>至少 10 位，建议由成员首次登录后更换。</small>
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => setShowCreateModal(false)}
              >
                取消
              </button>
              <button
                className="primary-button"
                disabled={adding || activeCount >= 5 || Boolean(accountHint)}
              >
                {adding ? "正在创建…" : "创建用户"}
              </button>
            </div>
            {activeCount < 5 && accountHint && (
              <small role="status" aria-live="polite">
                {accountHint}
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
                minLength="10"
                value={passwordForm.new_password}
                onChange={(event) =>
                  setPasswordForm({
                    ...passwordForm,
                    new_password: event.target.value,
                  })
                }
                required
              />
              <small>密码至少 10 位。修改成功后需要重新登录。</small>
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
                maxLength="500"
                rows="3"
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
