/** @typedef {{id: string, task_id: string, segment_key: string, task_title: string, task_revision: number, removed_by: string, deleted_at: string, scope: {listing?: string, store?: string}}} RecycledListing */
/** @typedef {"restore" | "purge"} RecycleAction */
/** @typedef {{items: RecycledListing[], action: RecycleAction}} RecycleSelection */
/** @typedef {RecycleSelection & import("./taskSegmentBatchActions").SegmentBatchResult} RecycleResult */
export {};
