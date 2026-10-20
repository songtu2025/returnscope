import { TaskDetailConfig } from "./TaskDetailConfig";
import { TaskEventList } from "./TaskEventList";

const DETAIL_TABS = [
  ["execution", "Listing"],
  ["events", "运行日志"],
  ["config", "任务配置"],
];

/** @param {{activeTab: string, disabled: boolean, onSelect: (value: string) => void}} props */
export function TaskDetailTabs({ activeTab, disabled, onSelect }) {
  return (
    <div className="task-detail-tabs" role="tablist" aria-label="任务详情视图">
      {DETAIL_TABS.map(([value, label]) => (
        <button
          key={value}
          type="button"
          role="tab"
          disabled={disabled}
          id={`task-tab-${value}`}
          aria-controls="task-view-panel"
          aria-selected={activeTab === value}
          className={activeTab === value ? "active" : ""}
          onClick={() => onSelect(value)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskEvent} TaskEvent */
/** @typedef {import("./taskRuntimeContracts").TaskSegment} TaskSegment */

/** @param {{task: AnalysisTask, events: TaskEvent[], focusListing: import("./TaskEventList").LogListingTarget | null}} props */
function TaskDetailEvents({ task, events, focusListing }) {
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
      <TaskEventList
        task={task}
        events={events}
        filterable
        focusListing={focusListing}
      />
    </section>
  );
}

/**
 * @param {{task: AnalysisTask, events: TaskEvent[], executableSegments: TaskSegment[],
 * activeTab: string, execution: import("react").ReactNode,
 * focusListing: import("./TaskEventList").LogListingTarget | null}} props
 */
export function TaskDetailViews({
  task,
  events,
  executableSegments,
  activeTab,
  execution,
  focusListing,
}) {
  return (
    <section
      className="task-detail-tab-panel"
      id="task-view-panel"
      role="tabpanel"
      tabIndex={-1}
      aria-labelledby={`task-tab-${activeTab}`}
    >
      {/* 页签往返保留明细与日志的临时状态，任务切换由上层 key 隔离。 */}
      <div hidden={activeTab !== "execution"}>{execution}</div>
      <div hidden={activeTab !== "events"}>
        <TaskDetailEvents task={task} events={events} focusListing={focusListing} />
      </div>
      {activeTab === "config" && (
        <TaskDetailConfig task={task} executableSegments={executableSegments} />
      )}
    </section>
  );
}
