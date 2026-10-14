import Button from "antd/es/button";
import { useState } from "react";

/** @typedef {import("./classificationStandardWorkspaceContracts").StandardWorkspaceContext} StandardWorkspaceContext */

/** @param {StandardWorkspaceContext} context */
export function StandardWorkspaceFooter(context) {
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const {
    draft,
    busy,
    dirty,
    onSave,
    onPublish,
    validationEvidence,
    publishDisabled,
    publishLabel,
    onDiscard,
    editable,
  } = context;
  return (
    <footer className="standard-editor-footer">
      <div role="status">
        <strong>{standardChangeStatus(context)}</strong>
        <span>
          {draft && !dirty ? "修改已暂存，尚未启用。" : ""}
          启用后用于新任务，运行中的任务不变。
        </span>
      </div>
      <div>
        {draft &&
          onDiscard &&
          (confirmDiscard ? (
            <>
              <span>放弃暂存及未保存的修改？</span>
              <Button disabled={Boolean(busy)} onClick={() => setConfirmDiscard(false)}>
                保留修改
              </Button>
              <Button
                danger
                disabled={Boolean(busy)}
                onClick={async () => {
                  await onDiscard();
                  setConfirmDiscard(false);
                }}
              >
                确认放弃
              </Button>
            </>
          ) : (
            <Button disabled={Boolean(busy)} onClick={() => setConfirmDiscard(true)}>
              放弃暂存修改
            </Button>
          ))}
        <Button disabled={Boolean(busy)} onClick={onSave}>
          {busy === "save" ? "暂存中" : "暂存修改"}
        </Button>
        <Button
          type="primary"
          disabled={publishDisabled || !editable}
          title={publishDisabled ? publishLabel : undefined}
          onClick={() => void onPublish(validationEvidence?.id ?? null)}
        >
          {busy === "publish" ? "保存并启用中" : publishLabel}
        </Button>
      </div>
    </footer>
  );
}

/** @param {StandardWorkspaceContext} context */
function standardChangeStatus({ isNew, draft, dirty, changeCount }) {
  return isNew && !draft
    ? dirty
      ? `有 ${changeCount} 项变更 · 未保存`
      : "尚未保存"
    : changeCount
      ? `有 ${changeCount} 项变更${dirty ? " · 未保存" : " · 已保存"}`
      : "暂无变更";
}
