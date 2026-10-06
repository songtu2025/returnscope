import { WarningCircle } from "@phosphor-icons/react";
import Button from "antd/es/button";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {ReturnType<typeof import("./taskRegistryPolicy").taskSummary>} TaskSummary */
/** @typedef {import("./taskRuntimeContracts").TaskSegment} TaskSegment */

/** @param {{task: AnalysisTask, modelServiceIssue: TaskSegment | undefined}} props */
function ModelServiceAlert({ task, modelServiceIssue }) {
  return (
    <>
      {modelServiceIssue && (
        <div className="task-model-service-alert" role="alert">
          <WarningCircle size={20} weight="fill" />
          <div>
            <b>
              {task.status === "paused" && task.pause_requested
                ? "模型服务异常，任务已自动暂停"
                : task.status === "paused"
                  ? "模型服务异常，任务已暂停"
                  : task.status === "failed"
                    ? "模型服务异常，执行已停止"
                    : "模型服务异常，请检查连接与运行日志"}
            </b>
            <span>{modelServiceIssue.error}</span>
          </div>
          <small>
            成功 {modelServiceIssue.model_calls || 0} · 失败{" "}
            {modelServiceIssue.model_failures || 0} · 缓存{" "}
            {modelServiceIssue.cache_hits || 0}
          </small>
        </div>
      )}
    </>
  );
}

/**
 * @param {{task: AnalysisTask, summary: TaskSummary, actionError: string,
 * retrySegment: TaskSegment | null, modelServiceIssue: TaskSegment | undefined,
 * onClearActionError: () => void}} props
 */
export function TaskDetailAlerts({
  task,
  summary,
  actionError,
  retrySegment,
  modelServiceIssue,
  onClearActionError,
}) {
  return (
    <>
      {actionError && !retrySegment && (
        <div className="task-action-error" role="alert">
          <WarningCircle size={18} />
          <span>{actionError}</span>
          <Button type="text" onClick={onClearActionError}>
            关闭
          </Button>
        </div>
      )}

      {["failed", "blocked", "partial"].includes(task.status) && task.message && (
        <section className="task-action-banner" role="status">
          <WarningCircle size={19} />
          <div>
            <b>{summary.issueDescription}</b>
            <p>{task.message}</p>
            <small>查看下方 Listing 的原因和可执行操作；已生成的结果仍可查看。</small>
          </div>
        </section>
      )}

      <ModelServiceAlert task={task} modelServiceIssue={modelServiceIssue} />
    </>
  );
}
