import { Modal } from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";

/** @param {{item: import("./TaskRecyclePage").RecycledListing}} props */
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

/** @param {{item: import("./TaskRecyclePage").RecycledListing, busy: boolean, onClose: () => void, onConfirm: () => void}} props */
export function TaskRecyclePurgeDialog({ item, busy, onClose, onConfirm }) {
  return (
    <Modal
      title={`永久删除 ${item.scope.listing || "Listing"}`}
      onClose={() => !busy && onClose()}
    >
      <div className="modal-form">
        <RecycleItemIdentity item={item} />
        <p>
          执行项及其独占检查点、旧导出文件将永久清理，无法恢复。已有分类结果、看板和必要来源信息保留。
        </p>
        <div className="modal-actions">
          <button className="secondary-button" disabled={busy} onClick={onClose}>
            返回
          </button>
          <button className="danger-button" disabled={busy} onClick={onConfirm}>
            {busy ? "正在删除…" : "确认永久删除"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
