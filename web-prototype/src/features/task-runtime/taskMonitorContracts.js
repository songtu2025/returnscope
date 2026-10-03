/**
 * @typedef {Object} TaskMonitorProps
 * @property {(message: string, type?: "success" | "error") => void} notify
 * @property {import("../../app/navigation").Navigate} onNavigate
 * @property {() => void | Promise<unknown>} onChanged
 * @property {string | null} [focusId]
 * @property {string | null} [focusSegmentId]
 * @property {TaskListState} [listState]
 * @property {(changes: Partial<TaskListState>) => void} [onListStateChange]
 * @property {(taskId: string | null) => void} [onTaskFocus]
 */

/** @typedef {{filter: string, query: string, owner: string, sort: string, attentionOnly: boolean}} TaskListState */

export {};
