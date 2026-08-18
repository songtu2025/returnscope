import { TaskMonitor } from "./TaskMonitor";

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
