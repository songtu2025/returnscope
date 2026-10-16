import { CaretRight, Check, WarningCircle } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { useRef } from "react";

/** @typedef {import("./taskCreateContracts").DataVersion} DataVersion */
/** @typedef {import("./taskCreateContracts").MysqlFormState} MysqlFormState */
/** @typedef {readonly [boolean, string, string, (() => void) | null]} SetupRow */

/**
 * @param {{prepared: boolean, planCounts?: import("../task-planning/taskPlanContracts").TaskPlanCounts, dataEntryMode: "mysql" | "upload", mysqlState: MysqlFormState, selectedReturns?: DataVersion, submitting: boolean, canContinue: boolean, launchStatus: string, submitError: string, submitLabel: string, onSubmit: () => void | Promise<void>}} props
 */

export function TaskLaunchActions({
  prepared,
  planCounts,
  dataEntryMode,
  mysqlState,
  selectedReturns,
  submitting,
  canContinue,
  launchStatus,
  submitError,
  submitLabel,
  onSubmit,
}) {
  const statusRef = useRef(/** @type {HTMLSpanElement | null} */ (null));
  return (
    <footer className={prepared ? "task-launch-actions" : "task-step-actions"}>
      {prepared && planCounts && (
        <b className="task-launch-scope">
          本次分析 {planCounts.listingCount} 个 Listing ·{" "}
          {planCounts.executable.toLocaleString()} 组评论
        </b>
      )}
      <span ref={statusRef} role="status" id="task-action-status" tabIndex={-1}>
        {launchStatusText({
          prepared,
          dataEntryMode,
          mysqlState,
          selectedReturns,
          launchStatus,
        })}
      </span>
      {prepared ? (
        <Button
          type="primary"
          className="primary-button"
          disabled={submitting || !canContinue}
          aria-describedby="task-action-status"
          onClick={() => {
            statusRef.current?.focus();
            void onSubmit();
          }}
        >
          {submitting ? "正在创建…" : submitError ? "重试创建" : submitLabel}
        </Button>
      ) : dataEntryMode === "mysql" ? (
        <Button
          type="primary"
          htmlType="submit"
          form="mysql-prepare-form"
          className="primary-button"
          disabled={!mysqlState.ready || Boolean(mysqlState.busy)}
        >
          {mysqlState.busy === "import" ? "正在准备…" : "准备分析"}
        </Button>
      ) : null}
    </footer>
  );
}

/** @param {{prepared: boolean, dataEntryMode: "mysql" | "upload", mysqlState: MysqlFormState, selectedReturns?: DataVersion, launchStatus: string}} state */
function launchStatusText({
  prepared,
  dataEntryMode,
  mysqlState,
  selectedReturns,
  launchStatus,
}) {
  if (prepared) return launchStatus;
  if (dataEntryMode === "mysql") {
    if (mysqlState.busy === "import") return "正在保存本次数据…";
    return mysqlState.ready
      ? `已选 ${mysqlState.rowCount.toLocaleString()} 条用户反馈`
      : "选择店铺和日期，查看本次分析范围";
  }
  return selectedReturns
    ? `已选 ${selectedReturns.row_count.toLocaleString()} 条用户反馈`
    : "请选择本次分析数据";
}

/**
 * @param {{onNavigate: import("../../app/navigation").Navigate, onUploadReturns: () => void, hasReturns: boolean, hasProducts: boolean, hasConfig: boolean, canManageModels?: boolean}} props
 */
export function SetupBlock({
  onNavigate,
  onUploadReturns,
  hasReturns,
  hasProducts,
  hasConfig,
  canManageModels = false,
}) {
  /** @type {SetupRow[]} */
  const rows = [
    [hasReturns, "导入用户反馈", "在当前分析任务中导入待分析数据", onUploadReturns],
    [
      hasProducts,
      "维护产品信息",
      "先建立系统统一复用的产品信息",
      () => onNavigate("data"),
    ],
    [
      hasConfig,
      hasConfig
        ? "模型服务已就绪"
        : canManageModels
          ? "发布模型配置"
          : "联系管理员发布模型配置",
      hasConfig
        ? "可使用已发布的模型配置"
        : canManageModels
          ? "先验证连接，再发布配置版本"
          : "模型服务由系统管理员维护，发布后可继续创建任务",
      canManageModels ? () => onNavigate("api") : null,
    ],
  ];
  return (
    <section className="setup-block">
      <WarningCircle size={28} />
      <div>
        <h2>还需要完成运行准备</h2>
        <p>真实任务必须同时具备用户反馈、产品信息和已发布模型配置。</p>
        <div className="setup-list">
          {rows.map(([done, title, note, action]) => (
            <button
              key={title}
              disabled={!done && !action}
              onClick={() => !done && action?.()}
              className={done ? "done" : ""}
            >
              <span>{done ? <Check size={16} /> : <CaretRight size={16} />}</span>
              <div>
                <b>{title}</b>
                <small>{note}</small>
              </div>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
