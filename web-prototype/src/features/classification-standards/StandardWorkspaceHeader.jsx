import { ArrowLeft } from "@phosphor-icons/react";

/** @typedef {import("./classificationStandardWorkspaceContracts").StandardWorkspaceContext} StandardWorkspaceContext */

/** @param {StandardWorkspaceContext} context */
export function StandardWorkspaceHeader({
  dirty,
  setConfirmBack,
  onBack,
  isNew,
  detail,
  draft,
  busy,
  onDelete,
}) {
  return (
    <div className="standard-subpage-heading editor-heading">
      <button
        type="button"
        className="icon-button"
        aria-label="返回"
        onClick={() => (dirty ? setConfirmBack(true) : onBack())}
      >
        <ArrowLeft size={18} />
      </button>
      <div>
        <h1>{isNew ? "建立品类与标签体系" : detail?.name}</h1>
        <span>
          {draft
            ? `未发布草稿 r${draft.revision} · 当前启用版本 V${draft.base_version_no}`
            : detail
              ? `${detail.status === "active" ? "当前启用版本" : "已停用版本"} V${detail.version_no}`
              : "新建标准"}
        </span>
      </div>
      {detail && (detail.status === "active" || detail.delete_mode === "delete") && (
        <details className="standard-more-menu">
          <summary>更多</summary>
          <button type="button" disabled={Boolean(busy)} onClick={onDelete}>
            {detail.delete_mode === "delete" ? "删除标准" : "停用标准"}
          </button>
        </details>
      )}
    </div>
  );
}
