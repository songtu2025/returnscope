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
 * @typedef {Object} ClassificationData
 * @property {string} [status]
 * @property {string[]} [primary_label_codes]
 * @property {string[]} [problem_label_codes]
 * @property {string[]} [positive_label_codes]
 * @property {string[]} [review_reasons]
 * @property {string} [taxonomy_version]
 * @property {string} [model_name]
 * @property {Array<{evidence?: string}>} [semantic_units]
 * @property {{label_correctness?: string, evidence_completeness?: string, review_routing?: string}} [human_review_assessment]
 * @property {SemanticReviewData} [semantic_review]
 * @property {SemanticReviewItem[]} [semantic_review_items]
 * @property {PersistedSemanticItemReview[]} [human_semantic_reviews]
 * @property {PersistedAddedSemanticItem[]} [human_added_semantic_items]
 * @property {CoverageReview} [coverage_review]
 *
 * @typedef {"change_label" | "remove" | "no_tag_needed"} SemanticReviewAction
 * @typedef {"complete" | "has_omission"} CoverageStatus
 * @typedef {{text?: string, source?: string}} SemanticEvidenceSpan
 *
 * @typedef {Object} SemanticReviewItem
 * @property {string} item_id
 * @property {string} [fact_id]
 * @property {string} evidence_text
 * @property {string} opinion
 * @property {string} [label_code]
 * @property {string[]} [label_path]
 * @property {string} disposition
 * @property {string} [reason]
 * @property {boolean} [business_review_required]
 * @property {string} [evidence_source]
 * @property {string | null} [diagnostic_domain]
 * @property {string | null} [diagnostic_code]
 * @property {string | null} [diagnostic_title]
 * @property {string | null} [detail_status]
 * @property {string | null} [primary_result]
 * @property {string | null} [secondary_result]
 * @property {string | null} [detail]
 * @property {string | null} [action]
 *
 * @typedef {Object} SemanticCoverageSummary
 * @property {number} [mapped]
 * @property {number} [no_tag_needed]
 * @property {number} [taxonomy_gap]
 * @property {number} [true_ambiguity]
 * @property {number} [analysis_failure]
 * @property {number} [unexplained_fragment_count]
 * @property {number} [total]
 * @property {boolean} [complete]
 *
 * @typedef {Object} SemanticReviewData
 * @property {SemanticReviewItem[]} [semantic_items]
 * @property {SemanticCoverageSummary} [coverage_summary]
 * @property {string[]} [unexplained_fragments]
 *
 * @typedef {Object} SemanticItemReview
 * @property {string} semantic_item_id
 * @property {SemanticReviewAction} action
 * @property {string | null} [label_code]
 * @property {string | null} [note]
 *
 * @typedef {Object} AddedSemanticItem
 * @property {string} [item_id]
 * @property {string} evidence_text
 * @property {string} opinion
 * @property {string} label_code
 * @property {string | null} [note]
 *
 * @typedef {SemanticItemReview & {assessed_by?: string, assessed_at?: string}} PersistedSemanticItemReview
 * @typedef {AddedSemanticItem & {assessed_by?: string, assessed_at?: string}} PersistedAddedSemanticItem
 * @typedef {{status?: CoverageStatus, assessed_by?: string, assessed_at?: string}} CoverageReview
 *
 * @typedef {Object} SemanticReviewSourceItem
 * @property {string} [semantic_item_id]
 * @property {string} [item_id]
 * @property {string} [fact_id]
 * @property {string} [factId]
 * @property {string} [id]
 * @property {string} [evidence_text]
 * @property {string} [evidence]
 * @property {SemanticEvidenceSpan[]} [evidence_spans]
 * @property {string} [evidence_source]
 * @property {string} [evidenceSource]
 * @property {string} [opinion]
 * @property {string} [fact_text_zh]
 * @property {string} [fact_summary]
 * @property {string} [summary]
 * @property {string} [label_code]
 * @property {string} [labelCode]
 * @property {string[]} [label_path]
 * @property {string[]} [taxonomy_path]
 * @property {string[]} [labelPath]
 * @property {string} [disposition]
 * @property {string} [status]
 * @property {string} [reason]
 * @property {string} [mapping_reason]
 * @property {string} [mappingReason]
 * @property {string | null} [diagnostic_domain]
 * @property {string} [diagnosticDomain]
 * @property {string | null} [diagnostic_code]
 * @property {string} [diagnosticCode]
 * @property {string} [code]
 * @property {string | null} [diagnostic_title]
 * @property {string} [diagnosticTitle]
 * @property {string} [title]
 * @property {string | null} [detail_status]
 * @property {string} [detailStatus]
 * @property {string | null} [primary_result]
 * @property {string} [primaryResult]
 * @property {string | null} [secondary_result]
 * @property {string} [secondaryResult]
 * @property {string | null} [detail]
 * @property {string} [diagnosticDetail]
 * @property {string | null} [action]
 * @property {string} [diagnosticAction]
 * @property {boolean} [business_review_required]
 * @property {boolean} [businessReviewRequired]
 * @property {boolean} [manual]
 *
 * @typedef {Object} SemanticReviewLedgerItem
 * @property {string} id
 * @property {string} evidence
 * @property {string} evidenceSource
 * @property {string} opinion
 * @property {string} labelCode
 * @property {string[]} labelPath
 * @property {string} disposition
 * @property {string} reason
 * @property {string} diagnosticDomain
 * @property {string} diagnosticCode
 * @property {string} diagnosticTitle
 * @property {string} detailStatus
 * @property {string} primaryResult
 * @property {string} secondaryResult
 * @property {string} diagnosticDetail
 * @property {string} diagnosticAction
 * @property {boolean | undefined} businessReviewRequired
 * @property {boolean} manual
 * @property {SemanticItemReview | null} [review]
 *
 * @typedef {{mapped: number, informational: number, needsReview: number, failures: number}} SemanticReviewSummary
 * @typedef {{items: SemanticReviewLedgerItem[], summary: SemanticReviewSummary, coverageStatus: CoverageStatus, suppliedSummary: SemanticReviewSummary | null}} SemanticReviewLedgerData
 *
 * @typedef {ClassificationData} ReviewClassification
 *
 * @typedef {Object} ReviewRecordFields
 * @property {string} id
 * @property {number} revision
 * @property {ReviewWorkflowStatus} workflow_status
 * @property {ReviewClassification} [classification]
 * @property {SemanticReviewData} [semantic_review]
 * @property {SemanticReviewItem[]} [semantic_review_items]
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
