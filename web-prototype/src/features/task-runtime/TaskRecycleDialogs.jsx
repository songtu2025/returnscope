import { Modal } from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";

/** @param {{item: import("./taskRecycleContracts").RecycledListing}} props */
export function RecycleItemIdentity({ item }) {
  return (
    <dl className="recycle-item-identity">
      <div>
        <dt>Listing</dt>
        <dd>{item.scope.listing || "--"}</dd>
      </div>
      <div>
        <dt>店铺 / 站点</dt>
        <dd>{item.scope.store || "--"}</dd>
      </div>
      <div>
        <dt>所属任务</dt>
        <dd>{item.task_title}</dd>
      </div>
      <div>
        <dt>任务标识</dt>
        <dd>{item.task_id}</dd>
      </div>
      <div>
        <dt>移除时间</dt>
        <dd>{formatTime(item.deleted_at)}</dd>
      </div>
    </dl>
  );
}

/** @param {{items: import("./taskRecycleContracts").RecycledListing[], action: import("./taskRecycleContracts").RecycleAction, busy: boolean, onClose: () => void, onConfirm: () => void}} props */
export function TaskRecycleActionDialog({ items, action, busy, onClose, onConfirm }) {
  const verb = action === "restore" ? "恢复" : "永久删除";
  return (
    <Modal
      title={
        items.length === 1
          ? `${verb} ${items[0].scope.listing || "Listing"}`
          : `${verb} ${items.length} 条记录`
      }
      className="recycle-confirm-dialog"
      onClose={() => !busy && onClose()}
    >
      <div className="modal-form recycle-confirm-form">
        <p>本次仅处理以下 {items.length} 条记录。</p>
        <div className="recycle-confirm-items" tabIndex={0} aria-label="待操作记录清单">
          {items.map((item) => (
            <RecycleItemIdentity key={item.id} item={item} />
          ))}
        </div>
        {action === "restore" ? (
          <p>恢复到所属任务，不会自动执行。</p>
        ) : (
          <p>
            执行项及其独占检查点、旧导出文件将永久清理，无法恢复。已有分类结果、看板和必要来源信息保留。
          </p>
        )}
        <div className="modal-actions">
          <button className="secondary-button" disabled={busy} onClick={onClose}>
            返回
          </button>
          <button
            className={action === "purge" ? "danger-button" : "primary-button"}
            disabled={busy}
            onClick={onConfirm}
          >
            {busy
              ? action === "restore"
                ? "正在恢复…"
                : "正在删除…"
              : `确认${verb}${items.length > 1 ? ` ${items.length} 条` : ""}`}
          </button>
        </div>
      </div>
    </Modal>
  );
}
