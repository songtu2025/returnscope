/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskSegment} TaskSegment */
/** @typedef {import("./taskRuntimeContracts").SegmentAction} SegmentAction */
/**
 * @typedef {Object} SegmentBoardRowProps
 * @property {AnalysisTask} task
 * @property {TaskSegment} segment
 * @property {{segmentIndex: number, page: number, pageSize: number, focusSegmentId?: string | null, focusedSegmentRef: import("react").RefObject<HTMLElement | null>, selection?: {selected: boolean, disabled: boolean, onToggle: () => void}}} position
 * @property {{canManageQueue: boolean, orderableKeys: string[], reordering: boolean, applyOrder: (segmentKeys: string[]) => Promise<void>}} queue
 * @property {{disabled?: boolean, expandedSegmentKey: string | null, setExpandedSegmentKey: import("react").Dispatch<import("react").SetStateAction<string | null>>, retryingPublishId: string | null, setRetryingPublishId: import("react").Dispatch<import("react").SetStateAction<string | null>>}} rowState
 * @property {{onAction: (segmentKey: string, action: SegmentAction, note?: string) => Promise<unknown>, onRetry: (segment: TaskSegment) => void, onViewClassification: (segment: TaskSegment & {result_version_id: string}, qualityStatus?: string) => void, onRetryPublish: (segmentId: string) => Promise<unknown>}} actions
 */

export {};
