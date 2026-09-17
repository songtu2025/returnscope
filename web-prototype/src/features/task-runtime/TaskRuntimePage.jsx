import { TaskMonitor } from "./TaskMonitor";
import "../../styles/task-flow.css";

/** @typedef {import("../../app/navigation").AppRoute} AppRoute */
/** @typedef {import("../../app/navigation").Navigate} Navigate */

/**
 * @param {{route: AppRoute, notify: (message: string, type?: "success" | "error") => void, onNavigate: Navigate, onChanged: () => void | Promise<unknown>}} props
 */

export function TaskRuntimePage({ route, notify, onNavigate, onChanged }) {
  return (
    <TaskMonitor
      notify={notify}
      onNavigate={onNavigate}
      onChanged={onChanged}
      focusId={route.query.task_id || route.query.task || null}
      focusSegmentId={route.query.segment_id || null}
    />
  );
}
