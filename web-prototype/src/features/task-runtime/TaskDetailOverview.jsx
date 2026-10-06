import Button from "antd/es/button";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {ReturnType<typeof import("./taskRegistryPolicy").taskSummary>} TaskSummary */

/** @param {{task: AnalysisTask, summary: TaskSummary, showListings: (filter: string) => void}} props */
function TaskAttention({ task, summary, showListings }) {
  return (
    <div>
      <span>需要处理</span>
      <b>
        {summary.issues || (summary.needsAttention ? "待确认" : 0)}
        {(!summary.needsAttention || summary.issues > 0) && <small> 个 Listing</small>}
      </b>
      {summary.needsAttention ? (
        <Button
          type="link"
          className="task-inline-action"
          onClick={() => showListings("attention")}
        >
          查看需处理事项
        </Button>
      ) : (
        <small>
          {task.status === "paused"
            ? "未完成部分已暂停，可随时继续"
            : "暂无需介入的问题"}
        </small>
      )}
    </div>
  );
}

/** @param {{task: AnalysisTask, summary: TaskSummary, showListings: (filter: string) => void}} props */
export function TaskDetailOverview({ task, summary, showListings }) {
  return (
    <section className="task-overview-band" aria-label="任务运行总览">
      <div className="task-overview-metrics">
        <div className="primary">
          <span>评论处理进度</span>
          <b>{Math.round(task.progress_percent || 0)}%</b>
          <small>
            {(task.progress_current || 0).toLocaleString()} /{" "}
            {(task.progress_total || 0).toLocaleString()} 组评论
          </small>
        </div>
        <div>
          <span>已生成结果</span>
          <b>
            {summary.generated}
            <small> / {summary.total} 个 Listing</small>
          </b>
          <small>{summary.resultDescription || "分析完成后生成结果"}</small>
        </div>
        <TaskAttention task={task} summary={summary} showListings={showListings} />
      </div>
    </section>
  );
}
