import { TaskDetailConfig } from "./TaskDetailConfig";
import { TaskEventList } from "./TaskEventList";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskEvent} TaskEvent */
/** @typedef {import("./taskRuntimeContracts").TaskSegment} TaskSegment */

/** @param {{task: AnalysisTask, events: TaskEvent[]}} props */
function TaskDetailEvents({ task, events }) {
  const isActive = ["queued", "running", "paused"].includes(task.status);
  return (
    <section className="task-secondary-section full-event-section">
      <header>
        <div>
          <h3>完整运行日志</h3>
          <p>来自后台执行器的真实事件，按时间倒序排列。</p>
        </div>
        <span className="live-tag">
          {isActive && <i />}
          {isActive ? "实时更新" : "完整记录"}
        </span>
      </header>
      <TaskEventList task={task} events={events} />
    </section>
  );
}

/**
 * @param {{task: AnalysisTask, events: TaskEvent[], executableSegments: TaskSegment[],
 * activeTab: string, execution: import("react").ReactNode}} props
 */
export function TaskDetailViews({
  task,
  events,
  executableSegments,
  activeTab,
  execution,
}) {
  return (
    <section
      className="task-detail-tab-panel"
      id="task-view-panel"
      role="tabpanel"
      aria-labelledby={`task-tab-${activeTab}`}
    >
      {activeTab === "execution" && execution}
      {activeTab === "events" && <TaskDetailEvents task={task} events={events} />}
      {activeTab === "config" && (
        <TaskDetailConfig task={task} executableSegments={executableSegments} />
      )}
    </section>
  );
}
