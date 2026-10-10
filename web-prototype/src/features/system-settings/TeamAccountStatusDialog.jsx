import { Modal } from "../../components/SharedUi";
import { Power } from "@phosphor-icons/react";
import { classNames, formatTime } from "../../lib/presentation";
/** @typedef {import("../../shared/api/systemSettingsContracts").TeamUser} TeamUser */
/** @typedef {import("../../shared/api/systemSettingsContracts").TeamInvitation} TeamInvitation */

/** @param {{statusTarget: TeamUser, setStatusTarget: (user: TeamUser | null) => void, statusNote: string, setStatusNote: (note: string) => void, statusUpdating: boolean, updateStatus: () => Promise<void>}} props */
export function TeamAccountStatusDialog({
  statusTarget,
  setStatusTarget,
  statusNote,
  setStatusNote,
  statusUpdating,
  updateStatus,
}) {
  return (
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
  );
}
