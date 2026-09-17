/**
 * @typedef {"overview" | "report" | "source" | "history"} DashboardTab
 * @typedef {Object} DashboardRoute
 * @property {string} dashboardId
 * @property {string} versionId
 * @property {string} reportId
 * @property {string} issueId
 * @property {DashboardTab} tab
 * @property {string} selectionToken
 * @property {"check" | "conflicts" | "confirm"} step
 * @property {string} status
 * @property {string} q
 * @property {number} page
 * @property {number} pageSize
 * @property {number} recordPage
 * @property {string} problem
 * @property {string} labelGroup
 * @property {string} listing
 * @property {string} productName
 * @property {string} productSku
 * @property {string} orderId
 * @property {string} dateFrom
 * @property {string} dateTo
 *
 * @typedef {(changes: Partial<DashboardRoute>, options?: {replace?: boolean}) => void} UpdateDashboardRoute
 * @typedef {(message: string, tone?: string) => void} DashboardNotify
 *
 * @typedef {Record<string, unknown> & {listing_count?: number, comment_count?: number, record_count?: number, unit_count?: number}} DashboardSummary
 *
 * @typedef {Object} DashboardVersion
 * @property {string} [version_id]
 * @property {string} [id]
 * @property {number} [version]
 * @property {string} [dataset_version_id]
 * @property {string} [reason]
 * @property {string} [created_by_name]
 * @property {string} [created_at]
 * @property {boolean} [is_current]
 * @property {string} [source_change_summary]
 * @property {DashboardSummary} [summary]
 *
 * @typedef {Object} DashboardListItem
 * @property {string} [id]
 * @property {string} [dashboard_id]
 * @property {string} [name]
 * @property {string} [description]
 * @property {"active" | "archived" | string} [status]
 * @property {string} [current_version_id]
 * @property {number} [current_version]
 * @property {number} [version]
 * @property {DashboardSummary} [summary]
 * @property {string} [updated_at]
 * @property {string} [created_at]
 * @property {string} [created_by_name]
 *
 * @typedef {DashboardListItem & {id: string, revision: number, version?: DashboardVersion}} Dashboard
 * @typedef {{items: DashboardListItem[], total: number, page: number, page_size: number}} DashboardListPage
 *
 * @typedef {Object} DashboardSource
 * @property {string} [version_id]
 * @property {string} [result_version_id]
 * @property {number} [version_no]
 * @property {number} [result_version_no]
 * @property {string} [product_dataset_name]
 * @property {number} [product_version]
 * @property {string} [store_site]
 * @property {string} [listing]
 * @property {number} [record_count]
 * @property {string} [quality_status]
 *
 * @typedef {Object} ReportIssue
 * @property {string} id
 *
 * @typedef {Object} ReportDecision
 * @property {string} issue_id
 * @property {string} status
 * @property {string} [report_id]
 * @property {string} [updated_at]
 * @property {string} [updated_by_name]
 *
 * @typedef {Object} InsightReport
 * @property {string} id
 * @property {string} status
 * @property {number | null} [version_no]
 * @property {number} [attempt_no]
 * @property {string} [prompt_version]
 * @property {LegacyInsightReportContent | InsightDecisionReportContent | null} [content]
 * @property {ReportDecision[]} [decisions]
 * @property {InsightReportEvidence | null} [evidence]
 * @property {string} [stage]
 * @property {string} [error]
 * @property {string} [model_name]
 * @property {string} [model_key]
 * @property {string} [resolved_model]
 * @property {string} [reasoning_effort]
 * @property {number} [dashboard_version_no]
 * @property {InsightReportQualityGate} [quality_gate]
 * @property {{input_tokens?: number, output_tokens?: number}} [usage]
 * @property {string} [completed_at]
 * @property {string} [evidence_hash]
 *
 * @typedef {{id: string, connection_id?: string, display_name?: string, model_key?: string, connection_name?: string, supported_efforts?: string[], active?: boolean, validation_status?: string}} InsightModel
 *
 * @typedef {Object} DashboardSelectionItem
 * @property {string} result_version_id
 * @property {number} result_version_no
 * @property {string} store_site
 * @property {string} listing
 * @property {string} quality_status
 * @property {number} record_count
 * @property {number} unit_count
 * @property {string[]} product_names
 * @property {string} published_at
 * @property {string} [version_id]
 * @property {string} [id]
 * @property {number} [version_no]
 * @property {string} [product_dataset_name]
 * @property {number} [product_version]
 *
 * @typedef {Object} DashboardSelection
 * @property {DashboardSelectionItem[]} selected
 * @property {string[]} [resolved_result_version_ids]
 * @property {Record<string, string | string[] | null>} [filters]
 * @property {"dashboard" | "insight"} [intent]
 * @property {string} [target_dashboard_id]
 * @property {number} [expected_revision]
 * @property {string} [updated_at]
 *
 * @typedef {Object} DashboardSelectionSource
 * @property {string} [version_id]
 * @property {string} [result_version_id]
 * @property {string} [id]
 * @property {number} [version]
 * @property {string | null} [store_site]
 * @property {string | null} [listing]
 * @property {string} [quality_status]
 * @property {string} [result_state]
 * @property {number} [record_count]
 * @property {number} [unit_count]
 * @property {string[]} [product_names]
 * @property {string | null} [product_name]
 * @property {string | null} [published_at]
 * @property {string} [created_at]
 *
 * @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultRecordResponse} DashboardRecord
 * @typedef {DashboardInsights | DashboardSource[]} DashboardContentData
 * @typedef {{loading: boolean, error: string, data: DashboardContentData | null}} DashboardContentState
 * @typedef {{loading: boolean, error: string, items: InsightReport[]}} DashboardReportState
 * @typedef {{issueId: string, loading: boolean, error: string}} DashboardDecisionState
 * @typedef {{modelId: string, effort: string}} InsightGenerationForm
 * @typedef {{label: string, value: string | number}} InsightEvidenceItem
 * @typedef {Record<string, InsightEvidenceItem>} InsightEvidenceCatalog
 * @typedef {{title: string, statement: string, tone?: "primary" | "neutral" | "warning", evidence_ids?: string[]}} ReportSummaryItem
 * @typedef {{id: string, kind: "structure" | "diagnostic" | "information", title: string, conclusion: string, interpretation: string, implication: string, evidence_ids: string[]}} ReportFinding
 * @typedef {{id: string, priority: "P0" | "P1" | "P2", target: string, action: string, rationale: string, success_signal: string, evidence_ids: string[]}} ReportAction
 * @typedef {{title?: string, executive_summary?: ReportSummaryItem[], findings?: ReportFinding[], actions?: ReportAction[], further_questions?: string[], caveats?: string[]}} LegacyInsightReportContent
 * @typedef {{status?: string, note?: string} & Record<string, unknown>} ReportDataQuality
 * @typedef {{status: string, label?: string, reason?: string}} ReportReadiness
 * @typedef {{status: string, text_quality?: ReportDataQuality, decision_readiness?: ReportReadiness}} InsightReportQualityGate
 * @typedef {{date_from?: string, date_to?: string}} ReportDateRange
 * @typedef {InsightReason & {trend_summary?: ReportTrendSummary, semantic_profile?: InsightSemanticProfile}} ReportReason
 * @typedef {{status?: string, window_weeks?: number, delta_percentage_points?: number, early_rate?: number, recent_rate?: number}} ReportTrendSummary
 * @typedef {{value?: string, product_reason_rate?: number, overall_reason_rate?: number, excess_record_count?: number, lift?: number} & Record<string, unknown>} ReportHotspot
 * @typedef {{comment?: string, reason?: string, product_name?: string} & Record<string, unknown>} ReportSample
 * @typedef {{reason_code?: string, selected_reason?: ReportReason, trend?: Array<{period_start: string, period_end: string, total_record_count?: number, percentage?: number, low_sample?: boolean}>, trend_summary?: ReportTrendSummary, hotspots?: ReportHotspot[], semantic_profile?: InsightSemanticProfile, samples?: ReportSample[]}} ReportDiagnostic
 * @typedef {{id?: string, reason_code?: string, role?: string, label?: string, label_group?: string, percentage?: number, record_count?: number, hotspot_label?: string, hotspots?: ReportHotspot[], trend_summary?: ReportTrendSummary, contexts?: {parts?: InsightPart[], opinions?: InsightOpinion[], samples?: ReportSample[]}, validation_focus?: string}} ReportBusinessIssue
 * @typedef {Object} InsightReportAnalysis
 * @property {InsightSummary} [summary]
 * @property {InsightReason[]} [label_group_breakdown]
 * @property {ReportDiagnostic[]} [diagnostics]
 * @property {ReportBusinessIssue[]} [business_issues]
 * @property {ReportReason[]} [reasons]
 * @typedef {Object} InsightReportSource
 * @property {ReportDateRange} [date_range]
 * @property {ReportDataQuality} [product_mapping]
 * @property {ReportDataQuality} [text_quality]
 * @property {string} [report_status]
 * @property {number} [label_coverage]
 * @property {{category_name?: string}} [report_profile]
 * @property {number} [pending_review_record_count]
 * @property {number} [included_record_count]
 * @property {number} [total_record_count]
 * @typedef {{analysis?: InsightReportAnalysis, source?: InsightReportSource, catalog?: InsightEvidenceCatalog}} InsightReportEvidence
 *
 * @typedef {{category?: string | null, listing?: string | null, product?: string | null, sku?: string | null}} ReportIssueScope
 * @typedef {{matched_return_samples?: number, scoped_return_samples?: number, return_sample_share?: number, baseline_return_sample_share?: number | null, gap_percentage_points?: number | null, lift?: number | null, recent_change_percentage_points?: number | null, trend_direction?: string}} ReportIssueMetrics
 * @typedef {{label?: string, validation_question?: string, rationale?: string, suggested_evidence?: string[]}} ReportIssueRecommendation
 * @typedef {Object} DecisionReportIssue
 * @property {string} id
 * @property {number} rank
 * @property {string} title
 * @property {ReportIssueScope} [scope]
 * @property {ReportIssueMetrics} [metrics]
 * @property {string[]} [known]
 * @property {string} [evidence_explanation]
 * @property {string[]} [unknown]
 * @property {ReportIssueRecommendation} [recommendation]
 * @property {ReportReadiness} [readiness]
 * @property {string[]} evidence_ids
 * @typedef {{report_type?: "problem_decision", title?: string, issues?: DecisionReportIssue[], caveats?: string[]}} InsightDecisionReportContent
 *
 * @typedef {{value: string, label: string, record_count: number, percentage: number, primary_rate?: number, subjects?: string[], lift?: number}} InsightReason
 * @typedef {InsightReason & {label_path?: string[], label_name?: string}} InsightHierarchyNode
 * @typedef {{value: string, record_count: number, total_record_count: number, product_reason_rate: number, lift: number}} InsightProduct
 * @typedef {{value: string, record_count: number}} InsightPart
 * @typedef {{opinion: string, part?: string, record_count: number}} InsightOpinion
 * @typedef {{record_count?: number, coverage?: number, parts?: InsightPart[], opinions?: InsightOpinion[]}} InsightSemanticProfile
 * @typedef {{items: DashboardRecord[], total: number}} InsightEvidence
 * @typedef {{listings?: string[], product_names?: string[], product_skus?: string[]}} InsightFilterOptions
 * @typedef {{date_from?: string, date_to?: string}} InsightDateRange
 * @typedef {Record<string, unknown> & {comment_count?: number, record_count?: number, total_comment_count?: number, total_record_count?: number, pending_review_comment_count?: number, pending_review_record_count?: number, comment_statuses?: Array<{status?: string, summary_status?: string, comment_count?: number, record_count?: number, count?: number}> | Record<string, number>, semantic_statuses?: Array<{status?: string, summary_status?: string, comment_count?: number, record_count?: number, count?: number}> | Record<string, number>}} InsightSummary
 * @typedef {Object} DashboardInsights
 * @property {InsightSummary} [summary]
 * @property {InsightReason[]} [reasons]
 * @property {InsightHierarchyNode[]} [hierarchy_problems]
 * @property {import("../../shared/api/reviewBatchContracts").ReviewTaxonomy} [taxonomy]
 * @property {InsightReason} [selected_reason]
 * @property {InsightProduct[]} [products]
 * @property {InsightReason[]} [co_reasons]
 * @property {InsightSemanticProfile} [semantic_profile]
 * @property {InsightEvidence} [evidence]
 * @property {InsightFilterOptions} [filter_options]
 * @property {InsightDateRange} [date_range]
 * @property {InsightReason[]} [subject_breakdown]
 * @property {string[]} [category_groups]
 * @property {number} [total_comment_count]
 * @property {number} [label_coverage]
 * @property {string} [group_alignment]
 * @property {Array<Record<string, unknown>>} [trend]
 * @property {Array<{status?: string, summary_status?: string, comment_count?: number, record_count?: number, count?: number}> | Record<string, number>} [comment_statuses]
 * @property {Array<{status?: string, summary_status?: string, comment_count?: number, record_count?: number, count?: number}> | Record<string, number>} [semantic_statuses]
 */

export {};
