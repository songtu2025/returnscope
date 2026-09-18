/**
 * @typedef {"queued" | "running" | "paused" | "completed" | "partial" | "blocked" | "failed" | "cancelled"} TaskStatus
 * @typedef {"ready" | "queued" | "running" | "pause_pending" | "cancel_pending" | "paused" | "completed" | "completed_with_errors" | "failed" | "blocked" | "cancelled" | "not_started" | "retry_pending"} TaskSegmentStatus
 * @typedef {"pause" | "resume" | "cancel"} SegmentAction
 *
 * @typedef {Object} TaskConfigSnapshot
 * @property {"connection" | "task"} [strategy_source]
 * @property {string} [connection]
 * @property {number} [version]
 * @property {string} [primary_model]
 * @property {"low" | "medium" | "high"} [primary_effort]
 *
 * @typedef {Object} TaskSegmentVariant
 * @property {string} category_a
 * @property {string} category_b
 * @property {number} [record_count]
 *
 * @typedef {Object} TaskSegment
 * @property {string} segment_key
 * @property {string} id
 * @property {string} agent_key
 * @property {string} agent_family
 * @property {{store?: string, listing?: string}} [scope]
 * @property {TaskSegmentStatus} status
 * @property {TaskSegmentStatus} [display_status]
 * @property {string} [requested_action]
 * @property {number} record_count
 * @property {number} unique_comments
 * @property {number} progress_current
 * @property {number} progress_total
 * @property {number} [model_calls]
 * @property {number} [model_failures]
 * @property {number} [cache_hits]
 * @property {TaskSegmentVariant[]} [variants]
 * @property {string} [standard_name]
 * @property {number} [standard_version]
 * @property {string} [logic_version]
 * @property {string} [taxonomy_version]
 * @property {number} [execution_order]
 * @property {string} [wait_reason]
 * @property {string} [error]
 * @property {string} [updated_at]
 * @property {string} [result_file_path]
 * @property {string} [result_version_id]
 * @property {number} [result_version]
 * @property {string} [result_publish_status]
 * @property {string} [result_publish_error]
 * @property {string} [result_quality_status]
 * @property {string} [result_state]
 * @property {string} [source_review_batch_id]
 * @property {boolean} [system_retry_available]
 * @property {number} [system_failure_count]
 *
 * @typedef {Object} AnalysisTask
 * @property {string} id
 * @property {string} title
 * @property {TaskStatus} status
 * @property {string} [stage]
 * @property {string} [message]
 * @property {number} revision
 * @property {string | null} [archived_at]
 * @property {TaskSegment[]} [segments]
 * @property {number} [listing_count]
 * @property {number} [progress_percent]
 * @property {number} [progress_current]
 * @property {number} [progress_total]
 * @property {string} owner_name
 * @property {string} created_at
 * @property {string} [updated_at]
 * @property {string} [store]
 * @property {string} [listing]
 * @property {string} [listing_search_text]
 * @property {string} [dataset_name]
 * @property {number} [dataset_version]
 * @property {string} [product_name]
 * @property {number} [product_version]
 * @property {string} [product_version_id]
 * @property {string} [config_version_id]
 * @property {string} [connection_name]
 * @property {number} [config_version]
 * @property {string} [primary_model]
 * @property {"low" | "medium" | "high"} [primary_effort]
 * @property {string} [result_file_path]
 * @property {boolean | number} [pause_requested]
 * @property {number} [max_parallel_segments]
 * @property {number} [owner_running_segments]
 * @property {number} [owner_segment_limit]
 * @property {{execution_plan?: {unresolved_policy?: string, summary?: {blocked_count?: number}}, config?: TaskConfigSnapshot}} [snapshot]
 *
 * @typedef {Object} TaskEventChange
 * @property {string} [title]
 * @property {TaskStatus} [status]
 *
 * @typedef {Object} TaskEvent
 * @property {string | number} id
 * @property {string} stage
 * @property {string} message
 * @property {string} created_at
 * @property {string} event_type
 * @property {string} [actor_name]
 * @property {{segment_id?: string, before?: TaskEventChange, after?: TaskEventChange, note?: string}} [data]
 *
 * @typedef {Record<string, unknown>} TaskPayload
 */

export {};
