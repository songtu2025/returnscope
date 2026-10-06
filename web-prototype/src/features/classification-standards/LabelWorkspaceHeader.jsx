import { ArrowCounterClockwise, Copy } from "@phosphor-icons/react";
import Button from "antd/es/button";
/** @typedef {import("./ClassificationLabelWorkbench").ClassificationLabelWorkbenchProps} WorkbenchProps */
/** @typedef {ReturnType<typeof import("./useClassificationLabelWorkbenchController").useClassificationLabelWorkbenchController>} Controller */
/** @param {{label: NonNullable<Controller["label"]>, notify: WorkbenchProps["notify"]}} props */
function LabelCode({ label, notify }) {
  return (
    <div className="label-code-line">
      <code>{label.code}</code>
      <button
        type="button"
        className="icon-button"
        aria-label="复制标签编码"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(label.code);
            notify("标签编码已复制");
          } catch {
            notify("复制失败，请选中编码手动复制", "error");
          }
        }}
      >
        <Copy size={14} />
      </button>
    </div>
  );
}
/** @param {Pick<Controller,"published"|"setPending"> & Pick<WorkbenchProps,"content"|"busy">} props */
function LabelRetirementMenu({ busy, content, published, setPending }) {
  return (
    <details className="standard-more-menu">
      <summary>更多</summary>
      <button
        type="button"
        disabled={Boolean(busy) || content.labels.length <= 1}
        onClick={(event) => {
          const menu = event.currentTarget.closest("details");
          if (menu) menu.open = false;
          setPending({ type: "retire" });
        }}
      >
        {published ? "停用标签" : "移除新标签"}
      </button>
    </details>
  );
}
/** @typedef {Pick<Controller,"removed"|"editing"|"setEditing"|"labelDirty"|"undoLabel"|"published"|"setPending"> & Pick<WorkbenchProps,"editable"|"busy"|"content">} WorkspaceActionsProps */
/** @param {WorkspaceActionsProps} props */
function LabelWorkspaceActions({
  editable,
  removed,
  editing,
  setEditing,
  labelDirty,
  busy,
  undoLabel,
  content,
  published,
  setPending,
}) {
  return (
    <div className="label-workspace-actions">
      {editable && !removed && (
        <Button onClick={() => setEditing((value) => !value)}>
          {editing ? "完成编辑" : "编辑"}
        </Button>
      )}
      {editable && labelDirty && (
        <Button
          disabled={Boolean(busy)}
          icon={<ArrowCounterClockwise size={15} />}
          onClick={undoLabel}
        >
          撤销当前修改
        </Button>
      )}
      {editable && !removed && (
        <LabelRetirementMenu
          busy={busy}
          content={content}
          published={published}
          setPending={setPending}
        />
      )}
    </div>
  );
}
/** @param {WorkspaceActionsProps & {label: NonNullable<Controller["label"]>, notify: WorkbenchProps["notify"]}} props */
export function LabelWorkspaceHeader({ label, notify, ...actions }) {
  return (
    <header>
      <div>
        <h2>{label.name || "新建标签"}</h2>
        <LabelCode label={label} notify={notify} />
      </div>
      <LabelWorkspaceActions {...actions} />
    </header>
  );
}
