import { useDismissibleDetails } from "../../hooks/useDismissibleDetails";
import { ArrowLeft } from "@phosphor-icons/react";
import { InlineLoading } from "../../components/SharedUi";

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
  updating,
}) {
  const { detailsProps, summaryProps } = useDismissibleDetails({ menu: true });
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
            ? "有暂存修改，尚未启用"
            : detail
              ? detail.status === "active"
                ? "使用中"
                : "已停用"
              : "新建标准"}
        </span>
      </div>
      <InlineLoading label="更新中…" compact active={updating} />
      {detail && (detail.status === "active" || detail.delete_mode === "delete") && (
        <details {...detailsProps} className="standard-more-menu">
          <summary {...summaryProps}>更多</summary>
          <button type="button" disabled={Boolean(busy)} onClick={onDelete}>
            {detail.delete_mode === "delete" ? "删除标准" : "停用标准"}
          </button>
        </details>
      )}
    </div>
  );
}
