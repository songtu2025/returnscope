import { CaretRight, Check, WarningCircle } from "@phosphor-icons/react";
import Button from "antd/es/button";

export function TaskLaunchActions({
  prepared,
  dataEntryMode,
  mysqlState,
  selectedReturns,
  submitting,
  canContinue,
  launchStatus,
  submitError,
  submitLabel,
  onSubmit,
  onPrepareExisting,
}) {
  return (
    <footer className={prepared ? "task-launch-actions" : "task-step-actions"}>
      <span role="status" id="task-action-status">
        {prepared
          ? launchStatus
          : dataEntryMode === "mysql"
            ? mysqlState.busy === "import"
              ? "正在保存本次数据…"
              : mysqlState.ready
                ? `已选 ${mysqlState.rowCount.toLocaleString()} 条退货记录`
                : "选择店铺和日期，查看本次分析范围"
            : selectedReturns
              ? `已选 ${selectedReturns.row_count.toLocaleString()} 条退货记录`
              : "请选择本次分析数据"}
      </span>
      {prepared ? (
        <Button
          type="primary"
          className="primary-button"
          disabled={submitting || !canContinue}
          aria-describedby="task-action-status"
          onClick={onSubmit}
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
      ) : (
        <Button
          type="primary"
          className="primary-button"
          disabled={!selectedReturns || submitting}
          onClick={onPrepareExisting}
        >
          准备分析
        </Button>
      )}
    </footer>
  );
}

export function SetupBlock({
  onNavigate,
  onUploadReturns,
  hasReturns,
  hasProducts,
  hasConfig,
}) {
  const rows = [
    [hasReturns, "导入退货明细", "在当前分析任务中导入待分析数据", onUploadReturns],
    [
      hasProducts,
      "维护产品信息",
      "先建立系统统一复用的产品信息",
      () => onNavigate("data"),
    ],
    [hasConfig, "发布模型配置", "先验证连接，再发布配置版本", () => onNavigate("api")],
  ];
  return (
    <section className="setup-block">
      <WarningCircle size={28} />
      <div>
        <h2>还需要完成运行准备</h2>
        <p>真实任务必须同时具备退货明细、产品信息和已发布模型配置。</p>
        <div className="setup-list">
          {rows.map(([done, title, note, action]) => (
            <button
              key={title}
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
