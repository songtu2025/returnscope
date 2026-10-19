/**
 * @typedef {Object} TaskMonitorProps
 * @property {string} [userId]
 * @property {(message: string, type?: "success" | "error") => void} notify
 * @property {import("../../app/navigation").Navigate} onNavigate
 * @property {() => void | Promise<unknown>} onChanged
 * @property {string | null} [focusId]
 * @property {string | null} [focusSegmentId]
 * @property {TaskListState} [listState]
 * @property {(changes: Partial<TaskListState>) => void} [onListStateChange]
 * @property {(taskId: string | null) => void} [onTaskFocus]
 * @property {string} [taskReturn]
 * @property {() => void} [onReturnResultPool]
 * @property {() => void} [onReturnRecycle]
 * @property {() => void} [onReturnProducts]
 * @property {import("./useSegmentBoardView").SegmentBoardReturnRef} [listingReturnState]
 * @property {import("react").MutableRefObject<import("../../hooks/useListReturnPosition").ListReturnPosition | null>} [returnPosition]
 */

/** @typedef {{filter: string, query: string, owner: string, ownerId?: string, sort: string, attentionOnly: boolean}} TaskListState */

export {};
