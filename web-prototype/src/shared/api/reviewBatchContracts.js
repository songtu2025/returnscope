/** @typedef {"draft" | "in_review" | "conflict" | "published"} ReviewBatchStatus */
/** @typedef {"pending" | "resolved" | "excluded"} ReviewWorkflowStatus */
/** @typedef {"confirm" | "modify" | "exclude"} ReviewAction */

/**
 * @typedef {Object} ReviewBatch
 * @property {string} id
 * @property {ReviewBatchStatus} status
 * @property {number} revision
 * @property {string} base_result_version_id
 * @property {number} [base_version_no]
 * @property {number} [base_record_count]
 * @property {number} [base_unit_count]
 * @property {string} [store_site]
 * @property {string} [listing]
 * @property {string} [creator_name]
 * @property {number} record_count
 * @property {number} resolved_count
 * @property {number} excluded_count
 * @property {number} remaining_count
 * @property {number} [pending_count]
 * @property {string} created_at
 * @property {string} updated_at
 * @property {string} [derived_result_version_id]
 * @property {number} [derived_version_no]
 * @property {string} [derived_quality_status]
 * @property {string} [derived_published_at]
 * @property {number} [unit_count]
 *
 * @typedef {Object} ReviewClassification
 * @property {string} [status]
 * @property {string[]} [primary_label_codes]
 * @property {string[]} [problem_label_codes]
 * @property {string[]} [review_reasons]
 * @property {string} [taxonomy_version]
 * @property {string} [model_name]
 * @property {Array<{evidence?: string}>} [semantic_units]
 * @property {{label_correctness?: string, evidence_completeness?: string, review_routing?: string}} [human_review_assessment]
 *
 * @typedef {Object} ReviewRecordFields
 * @property {string} id
 * @property {number} revision
 * @property {ReviewWorkflowStatus} workflow_status
 * @property {ReviewClassification} [classification]
 * @property {string} [comment]
 * @property {number} [record_count]
 * @property {string[]} [order_ids]
 * @property {string[]} [product_names]
 * @property {string[]} [listings]
 * @property {string[]} [source_skus]
 * @property {string[]} [matched_mskus]
 * @property {string[]} [product_skus]
 * @property {{label_correctness?: string, evidence_completeness?: string, review_routing?: string}} [human_review_assessment]
 *
 * @typedef {ReviewRecordFields & Record<string, unknown>} ReviewRecord
 * @typedef {import("./generated/classification-results/types.gen").ClassificationResultTaxonomyLabelResponse} ReviewLabel
 * @typedef {import("./generated/classification-results/types.gen").ClassificationResultTaxonomyResponse} ReviewTaxonomy
 * @typedef {import("./generated/classification-results/types.gen").ClassificationResultVersionResponse} ResultVersion
 *
 * @typedef {{items: ReviewBatch[], total: number, page: number, page_size: number}} ReviewBatchPage
 * @typedef {{items: ReviewRecord[], total: number, page: number, page_size: number, taxonomy?: ReviewTaxonomy | null}} ReviewRecordPage
 * @typedef {{version: number, version_id: string}} PublishedReviewVersion
 * @typedef {{message: string, serverRecord?: ReviewRecord}} ReviewConflict
 * @typedef {Error & {status?: number}} ReviewRequestError
 * @typedef {{id: string, revision: number, actor_name?: string, before: ReviewClassification, after: ReviewClassification, note?: string, created_at: string}} LegacyReviewRevision
 * @typedef {ReviewRecordFields & {classification: ReviewClassification & {status: string}, comment: string, task_title: string, owner_name: string, updated_at: string, base_result_version_id: string, revisions?: LegacyReviewRevision[]}} LegacyReviewRecord
 *
 * @typedef {Object} ReviewBatchRoute
 * @property {string} batchId
 * @property {string} resultVersionId
 * @property {string} status
 * @property {number} page
 * @property {number} pageSize
 * @property {string} listing
 * @property {string} productName
 * @property {string} productSku
 * @property {string} orderId
 * @property {string} q
 * @property {string} taskId
 * @property {string} segmentId
 * @property {string} returnTo
 *
 * @typedef {Object} ReviewRecordFilters
 * @property {string} q
 * @property {string} status
 * @property {string} listing
 * @property {string} productName
 * @property {string} productSku
 * @property {string} orderId
 */

export {};
