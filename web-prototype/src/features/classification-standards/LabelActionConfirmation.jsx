import Button from "antd/es/button";
import { Modal } from "../../components/SharedUi";
/** @typedef {import("./ClassificationLabelWorkbench").ClassificationLabelWorkbenchProps} WorkbenchProps */
/** @typedef {ReturnType<typeof import("./useClassificationLabelWorkbenchController").useClassificationLabelWorkbenchController>} Controller */
/** @param {Pick<Controller,"published"|"setPending"|"label"|"addLabel"|"retireLabel"> & {pending: NonNullable<Controller["pending"]>}} props */
export function LabelActionConfirmation({
  pending,
  published,
  setPending,
  label,
  addLabel,
  retireLabel,
}) {
  return (
    <Modal
      eyebrow="标签草稿"
      title={
        pending.type === "replace"
          ? "创建替代标签"
          : published
            ? "停用此标签？"
            : "移除新标签？"
      }
      onClose={() => setPending(null)}
    >
      <div className="label-action-confirm">
        <p>
          {pending.type === "replace"
            ? "将复制名称、判定说明和关键词，生成新编码，并将旧标签标记为拟停用。新标签不继承旧标签的承诺关联与专用校验规则；发布前请在标准设置中核对相关指令。"
            : "仅修改当前草稿。相关标签校验引用会同步清理，已发布标准和历史结果保持原样。"}
        </p>
        <div>
          <Button onClick={() => setPending(null)}>继续编辑</Button>
          <Button
            type="primary"
            onClick={() =>
              pending.type === "replace" ? addLabel(label) : retireLabel()
            }
          >
            {pending.type === "replace" ? "创建替代标签" : "确认移除"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
