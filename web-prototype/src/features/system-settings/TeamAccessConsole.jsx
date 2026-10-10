import { UserPlus } from "@phosphor-icons/react";
import { CardHeading } from "../../components/SharedUi";
import { classNames, formatTime } from "../../lib/presentation";
/** @typedef {import("../../shared/api/systemSettingsContracts").TeamUser} TeamUser */
/** @typedef {import("../../shared/api/systemSettingsContracts").TeamInvitation} TeamInvitation */

/** @param {string | null | undefined} value */
function formatLastLoginTime(value) {
  if (!value) return "--";
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return "--";
  // 固定转换到 UTC+8，避免浏览器所在地时区影响登录时间。
  const utcOffsetMilliseconds = 8 * 60 * 60 * 1000;
  return new Date(timestamp + utcOffsetMilliseconds)
    .toISOString()
    .slice(0, 19)
    .replace("T", " ");
}

/** @param {{users: TeamUser[], invitations: TeamInvitation[], currentUser?: {id?: string} | null, focusUserId: string | null, focusedUserRef: import("react").RefObject<HTMLTableRowElement | null>, onInvite: () => void, onEmail: () => void, onPassword: () => void, onStatusTarget: (user: TeamUser) => void, invitationAction: string, handleInvitation: (id: string, action: "resend" | "revoke") => Promise<void>}} props */
export function TeamAccessConsole({
  users,
  invitations,
  currentUser,
  focusUserId,
  focusedUserRef,
  onInvite,
  onEmail,
  onPassword,
  onStatusTarget,
  invitationAction,
  handleInvitation,
}) {
  const activeCount = users.filter((user) => Boolean(user.active)).length;
  return (
    <div className="team-layout">
      <section className="content-card access-console">
        <CardHeading
          title="访问控制台"
          note={`${activeCount} 个启用账号 · ${invitations.length} 个待注册`}
          action={
            <button
              type="button"
              className="primary-button compact-button"
              onClick={onInvite}
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
          <div
            className="access-table-scroll"
            role="region"
            aria-label="团队成员表格"
            tabIndex={0}
          >
            <table className="member-table" aria-label="团队成员">
              <thead>
                <tr>
                  <th scope="col">用户</th>
                  <th scope="col">邮箱</th>
                  <th scope="col">状态</th>
                  <th scope="col">最后登录时间（UTC+8）</th>
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
                      <td className="member-last-login">
                        {formatLastLoginTime(user.last_seen_at)}
                      </td>
                      <td>
                        <div className="member-actions">
                          {isCurrentUser ? (
                            <>
                              <button
                                type="button"
                                className="member-toggle"
                                onClick={onEmail}
                              >
                                修改邮箱
                              </button>
                              <button
                                type="button"
                                className="member-toggle"
                                onClick={onPassword}
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
                              onClick={() => onStatusTarget(user)}
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
                    <td colSpan={5}>暂无用户账号</td>
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
  );
}
