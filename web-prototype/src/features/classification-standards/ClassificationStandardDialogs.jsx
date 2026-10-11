import Button from "antd/es/button";
import { Modal } from "../../components/SharedUi";

/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardSummary} ClassificationStandardSummary */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardVersion} ClassificationStandardVersion */

/**
 * @param {{
 *   target: ClassificationStandardSummary | null,
 *   busy: string,
 *   onClose: () => void,
 *   onConfirm: () => void,
 * }} props
 */
export function ClassificationStandardDeleteDialog({
  target,
  busy,
  onClose,
  onConfirm,
}) {
  if (!target) return null;
  return (
    <Modal
      className="standard-lifecycle-modal"
      eyebrow={target.delete_mode === "delete" ? "删除分类标准" : "停用分类标准"}
      title={
        target.delete_mode === "delete"
          ? `永久删除“${target.name}”`
          : `停用“${target.name}”`
      }
      description={
        target.delete_mode === "delete"
          ? "该标准从未发布且未被任务使用，删除后无法恢复。"
          : "该标准已发布或已被任务使用。停用后新任务不再使用它，历史任务与结果保持不变。"
      }
      onClose={() => busy !== "delete" && onClose()}
    >
      {target.delete_mode !== "delete" && target.draft_id && (
        <p className="standard-deactivate-warning">
          此标准还有未发布草稿。停用时，草稿及其样本验证记录将一并删除，无法恢复。
        </p>
      )}
      <div className="standard-delete-actions">
        <Button disabled={busy === "delete"} onClick={onClose}>
          取消
        </Button>
        <Button type="primary" danger disabled={busy === "delete"} onClick={onConfirm}>
          {busy === "delete"
            ? "处理中"
            : target.delete_mode === "delete"
              ? "确认删除"
              : "确认停用"}
        </Button>
      </div>
    </Modal>
  );
}

/**
 * @param {{
 *   target: ClassificationStandardVersion | null,
 *   busy: string,
 *   onClose: () => void,
 *   onConfirm: () => void,
 * }} props
 */
export function ClassificationStandardRestoreDialog({
  target,
  busy,
  onClose,
  onConfirm,
}) {
  if (!target) return null;
  return (
    <Modal
      eyebrow="采用历史内容"
      title={`采用第 ${target.version_no} 次更新的内容？`}
      description="内容会暂存供你检查，保存并启用后才生效。修改记录保留。"
      onClose={onClose}
    >
      <div className="standard-delete-actions">
        <Button onClick={onClose}>取消</Button>
        <Button type="primary" disabled={busy === "restore"} onClick={onConfirm}>
          {busy === "restore" ? "采用中" : "采用内容"}
        </Button>
      </div>
    </Modal>
  );
}
