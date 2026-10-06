import { InfoRow } from "../../components/SharedUi";
import { EFFORT_LABELS } from "../../constants";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskSegment} TaskSegment */

/** @param {{task: AnalysisTask}} props */
function ModelConfiguration({ task }) {
  const snapshotConfig = task.snapshot?.config;
  const connectionName = snapshotConfig?.connection || task.connection_name || "—";
  const configVersion = snapshotConfig?.version ?? task.config_version ?? "—";
  const primaryModel = snapshotConfig?.primary_model || task.primary_model || "—";
  const primaryEffort = snapshotConfig?.primary_effort || task.primary_effort;
  const configSource =
    snapshotConfig?.strategy_source === "task"
      ? "任务自定义"
      : snapshotConfig?.strategy_source === "connection"
        ? "连接默认配置"
        : null;

  return (
    <>
      <InfoRow
        label="模型配置"
        value={`${connectionName} · #${configVersion}${
          configSource ? ` · ${configSource}` : ""
        }`}
      />
      <InfoRow
        label="主模型"
        value={`${primaryModel} · ${
          (primaryEffort && EFFORT_LABELS[primaryEffort]) || "—"
        }`}
      />
    </>
  );
}

/** @param {{task: AnalysisTask, executableSegments: TaskSegment[]}} props */
export function TaskDetailConfig({ task, executableSegments }) {
  const firstStandard = executableSegments.find((segment) => segment.standard_name);

  return (
    <section className="task-secondary-section task-config-panel">
      <header>
        <div>
          <h3>任务配置</h3>
          <p>任务运行期间始终使用创建时固化的版本。</p>
        </div>
      </header>
      <div className="task-config-body">
        <InfoRow label="分类标准" value={firstStandard?.standard_name || "—"} />
        <InfoRow label="并行数" value={task.max_parallel_segments ?? 3} />
        <InfoRow label="任务 ID" value={task.id} />
        <InfoRow
          label="退货明细"
          value={`${task.dataset_name || "—"} · v${task.dataset_version || "—"}`}
        />
        <InfoRow
          label="产品信息"
          value={`${task.product_name || "—"} · v${task.product_version || "—"}`}
        />
        <ModelConfiguration task={task} />
      </div>
    </section>
  );
}
