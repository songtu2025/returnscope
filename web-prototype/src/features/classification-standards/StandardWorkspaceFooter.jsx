import Button from "antd/es/button";

/** @typedef {import("./classificationStandardWorkspaceContracts").StandardWorkspaceContext} StandardWorkspaceContext */

/** @param {StandardWorkspaceContext} context */
export function StandardWorkspaceFooter(context) {
  const {
    draft,
    busy,
    dirty,
    onSave,
    section,
    setSection,
    setConfirmPublish,
    publishDisabled,
    publishLabel,
  } = context;
  return (
    <footer className="standard-editor-footer">
      <div role="status">
        <strong>{standardChangeStatus(context)}</strong>
        {draft && !dirty && <span>草稿 r{draft.revision}，尚未发布</span>}
      </div>
      <div>
        <Button disabled={Boolean(busy)} onClick={onSave}>
          {busy === "save" ? "保存中" : "保存草稿"}
        </Button>
        {section === "review" ? (
          <button
            type="button"
            className="primary-button"
            disabled={publishDisabled}
            title={publishDisabled ? publishLabel : undefined}
            onClick={() => setConfirmPublish(true)}
          >
            {busy === "publish" ? "启用中" : publishLabel}
          </button>
        ) : (
          <Button
            type="primary"
            disabled={Boolean(busy) || (!dirty && !draft)}
            onClick={() => setSection("review")}
          >
            发布
          </Button>
        )}
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
