import { useState } from "react";
import { useSWRConfig } from "swr";
import { DotsThreeVertical } from "@phosphor-icons/react";
import { Modal } from "./SharedUi";
import { useDismissibleDetails } from "../hooks/useDismissibleDetails";
import { changeDeliveryLifecycle } from "../shared/api/deliveryApi";
import { refreshServerState } from "../shared/serverState";
import { errorMessage } from "../shared/api/requestErrors";

/** @param {{kind:"result"|"dashboard"|"report",id:string,name:string,revision:number,deleted?:boolean,onChanged?:()=>void|Promise<void>}} props */
export function DeliveryLifecycleControls({
  kind,
  id,
  name,
  revision,
  deleted,
  onChanged,
}) {
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const { mutate } = useSWRConfig();
  const { detailsProps, summaryProps } = useDismissibleDetails();
  const label = { result: "分类结果", dashboard: "分析看板", report: "报告" }[kind];
  const submit = async () => {
    setSaving(true);
    setError("");
    try {
      await changeDeliveryLifecycle(kind, id, deleted ? "restore" : "delete", revision);
      setConfirming(false);
      await refreshServerState(mutate, [
        "classification-results",
        "analysis-dashboards",
        "analysis-tasks",
        "workbench",
        "data-assets",
      ]);
      await onChanged?.();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setSaving(false);
    }
  };
  return (
    <>
      {deleted ? (
        <button
          className="secondary-button compact-button"
          disabled={saving}
          onClick={submit}
        >
          {saving ? "正在恢复…" : `恢复${label}`}
        </button>
      ) : (
        <details className="task-more-actions" {...detailsProps}>
          <summary
            className="secondary-button compact-button"
            aria-label={`更多${label}操作：${name}`}
            {...summaryProps}
          >
            <DotsThreeVertical size={18} />
          </summary>
          <div>
            <button
              className="danger"
              type="button"
              onClick={() => setConfirming(true)}
            >
              删除{label}
            </button>
          </div>
        </details>
      )}
      {error && !confirming && <p role="alert">{error}</p>}
      {confirming && (
        <Modal
          title={`删除${label}：${name}`}
          onClose={() => {
            if (!saving) {
              setConfirming(false);
              setError("");
            }
          }}
        >
          <p>
            {kind === "report"
              ? "报告将移入已删除，可以恢复。看板及来源结果保留。"
              : kind === "result"
                ? "分类结果将移入“已删除”，可以恢复。存在看板引用或来源分析仍在执行时，无法删除。"
                : "看板将移入“已删除”，分类结果和报告记录保留。恢复不会启动分析或生成报告。"}
          </p>
          {error && <p role="alert">{error}</p>}
          <div className="modal-actions">
            <button
              className="secondary-button"
              disabled={saving}
              onClick={() => {
                setConfirming(false);
                setError("");
              }}
            >
              返回
            </button>
            <button className="primary-button" disabled={saving} onClick={submit}>
              {saving ? "正在删除…" : "确认删除"}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
