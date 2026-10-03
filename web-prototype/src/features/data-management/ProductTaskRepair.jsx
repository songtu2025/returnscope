import { ArrowRight } from "@phosphor-icons/react";
import { TaskCategoryCompletion } from "./TaskCategoryCompletion";

/** @typedef {import("./productMasterContracts").DatasetRecord} DatasetRecord */
/** @typedef {import("./productMasterContracts").TaskRepairContext} TaskRepairContext */
/** @typedef {import("./productMasterContracts").ProductMasterProps} ProductMasterProps */

/** @param {Pick<ProductMasterProps,"focus"|"taskDraft"|"onReturnToTask"|"notify"> & {selected: DatasetRecord|null,currentVersionId: string|undefined}} props */
export function ProductTaskRepair({
  focus,
  taskDraft,
  onReturnToTask,
  notify,
  selected,
  currentVersionId,
}) {
  return (
    <>
      {" "}
      {focus?.returnToTask && taskDraft && (
        <section className="task-return-banner" role="status">
          <div>
            <b>正在补充任务所需的商品信息</b>
            <p>{productRepairMessage(focus)}</p>
          </div>
          <button
            className="primary-button"
            disabled={!currentVersionId}
            onClick={() => {
              if (currentVersionId) onReturnToTask?.(currentVersionId);
            }}
          >
            返回任务并重新预检
            <ArrowRight size={17} />
          </button>
        </section>
      )}
      {focus?.returnToTask &&
        (focus.unresolvedProducts?.length ?? 0) > 0 &&
        selected && (
          <TaskCategoryCompletion
            dataset={selected}
            focus={focus}
            notify={notify}
            onReturnToTask={onReturnToTask}
          />
        )}
    </>
  );
}

/** @param {TaskRepairContext} focus */
function productRepairMessage(focus) {
  return focus.unresolvedProducts?.length
    ? `已定位 ${focus.unresolvedProducts.length.toLocaleString()} 个商品，影响 ${(focus.blockedCommentCount ?? 0).toLocaleString()} 条评论。`
    : "完成维度修改后，返回原任务并重新生成执行计划。";
}
