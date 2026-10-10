/** @typedef {import("../shared/api/systemSettingsContracts").TeamUser} TeamUser */
import { errorMessage, errorStatus } from "../shared/api/requestErrors";
import { TeamAccessConsole } from "../features/system-settings/TeamAccessConsole";
import { TeamInviteDialog } from "../features/system-settings/TeamInviteDialog";
import { TeamPasswordDialog } from "../features/system-settings/TeamPasswordDialog";
import { TeamAccountStatusDialog } from "../features/system-settings/TeamAccountStatusDialog";
import { useTeamAccounts } from "../features/system-settings/useTeamAccounts";
import { useEffect, useRef, useState } from "react";
import { WarningCircle } from "@phosphor-icons/react";
import { api } from "../api";
import { EmptyState, InlineLoading, PageHeading } from "../components/SharedUi";
import { EmailChangeModal } from "../components/EmailChangeModal";

/** @param {{notify: (message: string, tone?: string) => void, currentUser?: {id?: string, display_name?: string, email?: string, is_admin?: boolean} | null, focusPassword?: boolean, focusUserId?: string | null}} props */
export function TeamPage({
  notify,
  currentUser,
  focusPassword = false,
  focusUserId = null,
}) {
  const { users, invitations, loadState, loadError, load } = useTeamAccounts(notify);
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

  const currentAccount = users.find(
    (user) => String(user.id) === String(currentUser?.id),
  );
  const currentEmail = currentAccount?.email || currentUser?.email || "未提供邮箱";

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
      notify(errorMessage(error), "error");
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
      notify(errorMessage(error), "error");
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
      notify(errorMessage(error), "error");
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
      if (error instanceof Error && errorStatus(error) === 409) {
        await load();
        setStatusTarget(null);
        setStatusNote("");
      }
      notify(errorMessage(error), "error");
    } finally {
      setStatusUpdating(false);
    }
  };
  return (
    <div className="standard-page team-page">
      <PageHeading eyebrow="账号管理" title="用户与安全" />
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
                  load().catch((error) => notify(errorMessage(error), "error"))
                }
              >
                重新加载
              </button>
            }
          />
        </section>
      )}
      {loadState === "ready" && (
        <TeamAccessConsole
          users={users}
          invitations={invitations}
          currentUser={currentUser}
          focusUserId={focusUserId}
          focusedUserRef={focusedUserRef}
          onInvite={() => setShowInviteModal(true)}
          onEmail={() => setShowEmailModal(true)}
          onPassword={() => setShowPasswordModal(true)}
          onStatusTarget={(user) => {
            setStatusTarget(user);
            setStatusNote("");
          }}
          invitationAction={invitationAction}
          handleInvitation={handleInvitation}
        />
      )}
      {showInviteModal && (
        <TeamInviteDialog
          setShowInviteModal={setShowInviteModal}
          submit={submit}
          inviteEmail={inviteEmail}
          setInviteEmail={setInviteEmail}
          inviting={inviting}
        />
      )}
      {showEmailModal && (
        <EmailChangeModal
          currentEmail={currentEmail}
          notify={notify}
          onClose={() => setShowEmailModal(false)}
        />
      )}
      {showPasswordModal && (
        <TeamPasswordDialog
          setShowPasswordModal={setShowPasswordModal}
          changePassword={changePassword}
          passwordInputRef={passwordInputRef}
          passwordForm={passwordForm}
          setPasswordForm={setPasswordForm}
          changingPassword={changingPassword}
        />
      )}
      {statusTarget && (
        <TeamAccountStatusDialog
          statusTarget={statusTarget}
          setStatusTarget={setStatusTarget}
          statusNote={statusNote}
          setStatusNote={setStatusNote}
          statusUpdating={statusUpdating}
          updateStatus={updateStatus}
        />
      )}
    </div>
  );
}
