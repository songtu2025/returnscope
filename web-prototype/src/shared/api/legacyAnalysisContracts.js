/**
 * @typedef {Record<string, string | number | null | undefined>} AnalysisBarRow
 * @typedef {{total_records: number, listing_count: number, sku_count: number, text_records: number, text_coverage: number, review_records: number, review_rate: number, product_matched: number, product_match_rate: number, labeled_records?: number, label_coverage?: number}} AnalysisMetrics
 * @typedef {{code: string, name: string, group?: string, label_path?: string[]}} AnalysisProblemLabel
 * @typedef {{date_min?: string | null, date_max?: string | null, category_as: string[], category_bs: string[], listings: string[], skus: string[], asins: string[], reasons: string[], statuses: string[], claim_relations: string[], problem_labels: AnalysisProblemLabel[]}} AnalysisFilterOptions
 * @typedef {{status: string, text_records: number, labeled_records: number, label_coverage: number, review_records: number, review_rate: number, review_reasons?: Array<{name: string, records: number}>}} AnalysisQualityGate
 * @typedef {{id: string, title: string, store?: string, listing?: string, result_version?: number, completed_at?: string, dataset_name?: string, dataset_version?: number, primary_model?: string, owner_name?: string, delivery_scope?: string}} AnalysisTaskSummary
 *
 * @typedef {{
 *   listing: string,
 *   records: number,
 *   text_rate: number,
 *   label_coverage: number,
 *   unknown_rate: number,
 *   review_rate: number,
 * }} AnalysisQualityRow
 *
 * @typedef {{
 *   code: string,
 *   name: string,
 *   group?: string,
 *   records: number,
 *   listing_coverage: number,
 *   top_listing_share: number,
 *   coverage_label: string,
 * }} ListingProblemRow
 *
 * @typedef {{
 *   metrics: AnalysisMetrics,
 *   top_problems: AnalysisBarRow[],
 *   listing_quality: AnalysisQualityRow[],
 *   listing_problems?: ListingProblemRow[],
 *   size_directions?: AnalysisBarRow[],
 *   parts: AnalysisBarRow[],
 * }} AnalysisOverview
 *
 * @typedef {{
 *   code: string,
 *   name: string,
 *   group?: string,
 *   records: number,
 *   share: number,
 *   change_pp: number,
 *   sku_count: number,
 *   top_sku_share: number,
 *   multi_problem_records: number,
 *   review_records: number,
 * }} DiagnosisPriority
 *
 * @typedef {{
 *   classification_key: string,
 *   listing?: string,
 *   sku?: string,
 *   reason?: string,
 *   comment: string,
 *   evidence?: string,
 * }} DiagnosisComment
 *
 * @typedef {{
 *   focus_code?: string,
 *   priorities?: DiagnosisPriority[],
 *   product_locations: AnalysisBarRow[],
 *   reasons: AnalysisBarRow[],
 *   parts: AnalysisBarRow[],
 *   pairs: AnalysisBarRow[],
 *   comments?: DiagnosisComment[],
 * }} AnalysisDiagnosis
 *
 * @typedef {{label: string, records: number}} ProductMatrixValue
 * @typedef {{name: string, values: ProductMatrixValue[]}} ProductMatrixRow
 * @typedef {{
 *   name: string,
 *   records: number,
 *   text_coverage: number,
 *   review_records: number,
 *   review_rate: number,
 *   top_problem?: string,
 * }} ProductSummaryRow
 * @typedef {{dimension: string, matrix?: ProductMatrixRow[], summary?: ProductSummaryRow[]}} AnalysisProducts
 *
 * @typedef {{review_comments: number, conflicts: number, unknown_records: number}} QualityMetrics
 * @typedef {{records: number, reason?: string, comment?: string, opinion?: string, unmapped_reason?: string}} UnknownSemanticRow
 * @typedef {{
 *   metrics: QualityMetrics,
 *   listing_quality: AnalysisQualityRow[],
 *   statuses: AnalysisBarRow[],
 *   review_reasons: AnalysisBarRow[],
 *   unknowns?: UnknownSemanticRow[],
 * }} AnalysisQuality
 *
 * @typedef {{
 *   order_id?: string,
 *   return_date?: string,
 *   sku?: string,
 *   asin?: string,
 *   listing?: string,
 *   category_b?: string,
 *   reason?: string,
 *   primary_labels?: string,
 *   problem_labels?: string,
 *   status?: string,
 *   comment?: string,
 * }} AnalysisDetailRecord
 * @typedef {{total: number, page: number, pages: number, records?: AnalysisDetailRecord[]}} AnalysisDetails
 * @typedef {{
 *   task: AnalysisTaskSummary,
 *   filters: AnalysisFilterOptions,
 *   scope: {total_records: number, filtered_records: number},
 *   overview: AnalysisOverview,
 *   quality_gate: AnalysisQualityGate,
 *   view: string,
 *   diagnosis: AnalysisDiagnosis,
 *   products: AnalysisProducts,
 *   quality: AnalysisQuality,
 *   details: AnalysisDetails,
 * }} LegacyAnalysis
 */

export {};
