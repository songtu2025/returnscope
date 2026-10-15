import { useRef, useState } from "react";
import { DotsThreeVertical } from "@phosphor-icons/react";
import { Modal } from "../../components/SharedUi";
import { useDismissibleDetails } from "../../hooks/useDismissibleDetails";

/** @param {Pick<import("./segmentBoardRowContracts").SegmentBoardRowProps, "segment" | "actions"> & {disabled?: boolean}} props */
export function SegmentRemovalControls({ segment, actions, disabled = false }) {
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const { detailsProps, summaryProps } = useDismissibleDetails({
    menu: true,
    disabled,
  });
  const name = segment.scope?.listing || segment.segment_key;
  const remove = async () => {
    if (savingRef.current || disabled) return;
    savingRef.current = true;
    setSaving(true);
    try {
      const success = await actions.onAction(segment.segment_key, "delete");
      if (success) setConfirming(false);
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };
  return (
    <>
      <details {...detailsProps} className="task-more-actions">
        <summary {...summaryProps} aria-label={`更多 Listing 操作：${name}`}>
          <DotsThreeVertical size={18} />
        </summary>
        <div>
          <button
            className="danger"
            disabled={disabled}
            onClick={() => setConfirming(true)}
          >
            移除 Listing
          </button>
        </div>
      </details>
      {confirming && (
        <Modal title={`移除 ${name}`} onClose={() => !saving && setConfirming(false)}>
          <p>
            此 Listing
            将移入回收站，不再参与任务执行和统计。正在执行的内容会先保存并停止；已有分类结果和看板保留。
          </p>
          <div className="modal-actions">
            <button
              className="secondary-button"
              disabled={saving}
              onClick={() => setConfirming(false)}
            >
              返回
            </button>
            <button
              className="primary-button"
              disabled={saving || disabled}
              onClick={remove}
            >
              {saving ? "正在提交…" : "确认移除 Listing"}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
