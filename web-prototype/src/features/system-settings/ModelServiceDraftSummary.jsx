import { WarningCircle } from "@phosphor-icons/react";

/** @param {Pick<import("./modelServiceViewContracts").ModelServiceSummaryProps, "draftVersion" | "activeVersion" | "busy" | "validationActive" | "discardConfirmation" | "onCancelDiscard" | "onDiscardDraft" | "onPublishDraft" | "onContinueDraft" | "onConfirmDiscard">} props */

export function ModelServiceDraftSummary({
  draftVersion,
  activeVersion,
  busy,
  validationActive,
  discardConfirmation,
  onCancelDiscard,
  onDiscardDraft,
  onPublishDraft,
  onContinueDraft,
  onConfirmDiscard,
}) {
  if (!draftVersion) return null;
  return (
    <section className="model-service-draft-strip">
      <ModelServiceDraftCopy
        draftVersion={draftVersion}
        activeVersion={activeVersion}
      />
      {discardConfirmation ? (
        <div className="model-service-discard-confirmation">
          <span>放弃后不可恢复</span>
          <button
            className="text-button"
            onClick={onCancelDiscard}
            disabled={Boolean(busy)}
          >
            取消
          </button>
          <button
            className="danger-button"
            onClick={onDiscardDraft}
            disabled={Boolean(busy)}
          >
            {busy === "discard-draft" ? "放弃中…" : "确认放弃"}
          </button>
        </div>
      ) : (
        <div className="model-service-draft-actions">
          <button
            className="primary-button"
            onClick={
              draftVersion.validation_status === "validated"
                ? onPublishDraft
                : onContinueDraft
            }
            disabled={Boolean(busy) || validationActive}
          >
            {draftVersion.validation_status === "validated" ? "发布版本" : "继续处理"}
          </button>
          <button
            className="text-button"
            onClick={onConfirmDiscard}
            disabled={Boolean(busy) || validationActive}
          >
            放弃草稿
          </button>
        </div>
      )}
    </section>
  );
}

/** @param {{draftVersion: NonNullable<import("./modelServiceViewContracts").ModelServiceSummaryProps["draftVersion"]>, activeVersion: import("./modelServiceViewContracts").ModelServiceSummaryProps["activeVersion"]}} props */
function ModelServiceDraftCopy({ draftVersion, activeVersion }) {
  return (
    <div className="model-service-draft-copy">
      <WarningCircle size={22} weight="duotone" />
      <p>
        <b>
          草稿 #{draftVersion.version} ·{" "}
          {draftVersion.validation_status === "validated"
            ? "可发布"
            : draftVersion.validation_status === "failed"
              ? "验证失败"
              : "待验证"}
        </b>
        <span>
          {draftVersion.change_note || "未填写变更说明"}；当前运行
          {activeVersion ? ` #${activeVersion.version}` : ""} 不受影响
        </span>
      </p>
    </div>
  );
}
