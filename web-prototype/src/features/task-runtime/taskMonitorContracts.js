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

/**
 * @typedef {Object} TaskDetailProps
 * @property {import("./taskRuntimeContracts").AnalysisTask} task
 * @property {(disabled: boolean) => import("react").ReactNode} [headerAction]
 * @property {import("./useSegmentBoardView").SegmentBoardReturnRef} [listingReturnState]
 * @property {string | null} [focusSegmentId]
 * @property {import("./taskRuntimeContracts").TaskEvent[]} events
 * @property {(segment: import("./taskRuntimeContracts").TaskSegment & {result_version_id: string}, qualityStatus?: string, systemRerunRequired?: string) => void} onViewClassification
 * @property {string} actionError
 * @property {() => void} onClearActionError
 * @property {(task: import("./taskRuntimeContracts").AnalysisTask) => Promise<unknown>} onTaskRenamed
 * @property {() => void} [onCreateSimilar]
 * @property {() => void | Promise<unknown>} onArchive
 * @property {() => void | Promise<unknown>} onPause
 * @property {(payload: import("./taskRuntimeContracts").TaskPayload) => Promise<boolean>} onResume
 * @property {() => void | Promise<unknown>} onRetry
 * @property {(segmentKey: string, payload: import("./taskRuntimeContracts").TaskPayload) => Promise<boolean>} onRetrySegment
 * @property {(segmentId: string) => Promise<boolean>} onRetryResultPublish
 * @property {(segmentKey: string, action: import("./taskRuntimeContracts").SegmentAction, note?: string) => Promise<boolean>} onSegmentAction
 * @property {import("./taskSegmentBatchActions").ApplySegmentBatch} [onBatchSegmentAction]
 * @property {() => Promise<boolean>} [onRefreshSegments]
 * @property {(maxParallelSegments: number) => Promise<boolean>} onParallelism
 * @property {(segmentKeys: string[]) => Promise<boolean>} onReorderSegments
 * @property {(payload: import("./taskRuntimeContracts").TaskPayload) => Promise<import("../task-planning/taskPlanContracts").TaskExecutionPlan>} onPreflightReplan
 * @property {(payload: import("./taskRuntimeContracts").TaskPayload) => Promise<boolean>} onReplan
 */

export {};
