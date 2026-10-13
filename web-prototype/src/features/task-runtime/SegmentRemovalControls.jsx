import { useState } from "react";
import { DotsThreeVertical } from "@phosphor-icons/react";
import { Modal } from "../../components/SharedUi";
import { useDismissibleDetails } from "../../hooks/useDismissibleDetails";

/** @param {Pick<import("./segmentBoardRowContracts").SegmentBoardRowProps, "segment" | "actions">} props */
export function SegmentRemovalControls({ segment, actions }) {
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);
  const { detailsProps, summaryProps } = useDismissibleDetails();
  const name = segment.scope?.listing || segment.segment_key;
  const remove = async () => {
    setSaving(true);
    const success = await actions.onAction(segment.segment_key, "delete");
    setSaving(false);
    if (success) setConfirming(false);
  };
  if (segment.deleted_at)
    return (
      <button
        className="secondary-button compact-button"
        disabled={saving}
        onClick={async () => {
          setSaving(true);
          await actions.onAction(segment.segment_key, "restore");
          setSaving(false);
        }}
      >
        {saving ? "正在恢复…" : "恢复 Listing"}
      </button>
    );
  const canCancel =
    ["queued", "retry_pending", "not_started", "running", "paused", "failed"].includes(
      segment.status,
    ) && !segment.requested_action;
  const canDelete =
    ["completed", "completed_with_errors", "failed", "cancelled"].includes(
      segment.status,
    ) && !segment.requested_action;
  if (!canCancel && !canDelete) return null;
  return (
    <>
      <details {...detailsProps} className="task-more-actions">
        <summary {...summaryProps} aria-label={`更多 Listing 操作：${name}`}>
          <DotsThreeVertical size={18} />
        </summary>
        <div>
          {canCancel && (
            <button onClick={() => actions.onCancel(segment)}>取消此 Listing</button>
          )}
          {canDelete && (
            <button className="danger" onClick={() => setConfirming(true)}>
              删除此 Listing
            </button>
          )}
        </div>
      </details>
      {confirming && (
        <Modal title={`删除 ${name}`} onClose={() => !saving && setConfirming(false)}>
          <p>
            此 Listing
            将移入“已删除”，不再参与任务执行和统计。已发布的分类结果和看板保留，可以恢复；恢复不会自动开始分析。
          </p>
          <div className="modal-actions">
            <button
              className="secondary-button"
              disabled={saving}
              onClick={() => setConfirming(false)}
            >
              返回
            </button>
            <button className="primary-button" disabled={saving} onClick={remove}>
              {saving ? "正在删除…" : "确认删除 Listing"}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
