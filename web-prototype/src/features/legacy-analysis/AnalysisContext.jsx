import { CheckCircle, DownloadSimple, WarningCircle } from "@phosphor-icons/react";
import { formatNumber, formatTime } from "../../lib/presentation";

/** @typedef {import("../../shared/api/legacyAnalysisContracts").LegacyAnalysis} LegacyAnalysis */
/** @typedef {import("../task-runtime/taskRuntimeContracts").AnalysisTask & {result_version?: number, completed_at?: string}} AnalysisResultTask */
/** @typedef {{kind: "result", id: string, listing?: string}} ResultsFocus */
/** @typedef {{task: AnalysisResultTask, tasks: AnalysisResultTask[], selectedId: string | null, analysis: LegacyAnalysis | null, filters: import("./AnalysisFilters").AnalysisFilterValues, focus?: ResultsFocus | null, onChangeTask: (id: string) => void, onNavigate: import("../../app/navigation").Navigate, onQuality: () => void, downloadUrl: string}} AnalysisContextProps */

/** @param {Pick<AnalysisContextProps, "tasks" | "selectedId" | "focus" | "onChangeTask">} props */
function AnalysisTaskPicker({ tasks, selectedId, focus, onChangeTask }) {
  return (
    <div className="analysis-task-picker">
      <label htmlFor="analysis-task">分析任务</label>
      <select
        id="analysis-task"
        value={selectedId ?? ""}
        onChange={(event) => onChangeTask(event.target.value)}
      >
        {tasks.map((item) => (
          <option key={item.id} value={item.id}>
            {item.title}
            {item.status === "cancelled" ? "（部分结果）" : ""}
            {!["completed", "cancelled"].includes(item.status)
              ? `（${focus?.listing ?? "已完成 Listing"} 阶段结果）`
              : ""}
          </option>
        ))}
      </select>
    </div>
  );
}

/** @param {Pick<AnalysisContextProps, "task" | "analysis"> & {isListingDelivery: boolean}} props */
function AnalysisTaskMeta({ task, analysis, isListingDelivery }) {
  return (
    <div className="analysis-context-meta">
      <b>
        {task.store}
        {task.listing ? ` · ${task.listing}` : ""}
      </b>
      <span>
        {isListingDelivery
          ? "Listing 结果"
          : task.status === "cancelled"
            ? "部分结果"
            : "结果"}{" "}
        v{analysis?.task?.result_version ?? task.result_version} · {task.dataset_name} v
        {task.dataset_version} ·{" "}
        {formatTime(analysis?.task?.completed_at ?? task.completed_at)}
      </span>
    </div>
  );
}

/** @param {Omit<AnalysisContextProps, "onNavigate" | "onQuality"> & {isListingDelivery: boolean}} props */
function AnalysisContextBar({
  task,
  tasks,
  selectedId,
  analysis,
  filters,
  focus,
  onChangeTask,
  downloadUrl,
  isListingDelivery,
}) {
  return (
    <section className="analysis-context-bar">
      <AnalysisTaskPicker
        tasks={tasks}
        selectedId={selectedId}
        focus={focus}
        onChangeTask={onChangeTask}
      />
      <AnalysisTaskMeta
        task={task}
        analysis={analysis}
        isListingDelivery={isListingDelivery}
      />
      <a className="primary-button" href={downloadUrl}>
        <DownloadSimple size={18} />
        {isListingDelivery
          ? `下载 ${filters.listing} 结果`
          : task.status === "cancelled"
            ? "下载部分结果"
            : "下载当前结果"}
      </a>
    </section>
  );
}

/** @param {Pick<AnalysisContextProps, "onNavigate" | "onQuality"> & {analysis: LegacyAnalysis}} props */
function AnalysisQualityWarning({ analysis, onNavigate, onQuality }) {
  const primaryQualityReason = analysis?.quality_gate?.review_reasons?.[0]?.name;
  const qualityAction = primaryQualityReason?.includes("品类")
    ? { page: "data", label: "补充商品信息" }
    : { page: "api", label: "检查模型配置" };
  return (
    <div className="plan-state warning result-quality-warning" role="alert">
      <WarningCircle size={19} />
      <div>
        <b>本批结果尚不能用于问题分析</b>
        <p>
          {formatNumber(analysis.quality_gate.text_records)} 条有效评论中，
          {formatNumber(analysis.quality_gate.labeled_records)} 条形成问题标签；
          {formatNumber(analysis.quality_gate.review_records)} 条进入人工复核。
          当前没有可聚合的问题标签，因此图表为空。
          {primaryQualityReason && ` 最常见复核原因：${primaryQualityReason}。`}
        </p>
      </div>
      <div className="result-quality-actions">
        <button className="secondary-button" onClick={onQuality}>
          查看复核原因
        </button>
        <button
          className="primary-button"
          onClick={() => onNavigate(qualityAction.page)}
        >
          {qualityAction.label}
        </button>
      </div>
    </div>
  );
}

function PartialResultNotice() {
  return (
    <div className="plan-state warning" role="status">
      <WarningCircle size={19} />
      <div>
        <b>当前为部分结果</b>
        <p>仅包含取消前已经完成的 Listing 片段；未完成片段未计入本页指标。</p>
      </div>
    </div>
  );
}

/** @param {AnalysisContextProps} props */
export function AnalysisContext(props) {
  const { task, analysis, filters, onNavigate, onQuality } = props;
  const isListingDelivery = task && !["completed", "cancelled"].includes(task.status);
  const resultUnavailable = analysis?.quality_gate?.status === "unusable";
  return (
    <>
      <AnalysisContextBar {...props} isListingDelivery={isListingDelivery} />
      {isListingDelivery && analysis && !resultUnavailable && (
        <div className="plan-state success" role="status">
          <CheckCircle size={19} />
          <div>
            <b>{filters.listing} 已完成，可以先查看和下载</b>
            <p>
              本页只统计该 Listing 的已交付结果；批量任务中的其他 Listing 继续独立运行。
            </p>
          </div>
        </div>
      )}
      {analysis && resultUnavailable && (
        <AnalysisQualityWarning
          analysis={analysis}
          onNavigate={onNavigate}
          onQuality={onQuality}
        />
      )}
      {task.status === "cancelled" && <PartialResultNotice />}
    </>
  );
}
