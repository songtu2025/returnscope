/**
 * @typedef {{
 *   stores?: string[],
 *   valid_comment_rows?: number,
 *   matching_key_ready_rate?: number,
 *   missing_store_rows?: number,
 *   complete_rate?: number,
 * }} DatasetQuality
 *
 * @typedef {{
 *   id: string,
 *   version_id?: string,
 *   dataset_id?: string,
 *   version: number,
 *   row_count?: number,
 *   original_name?: string,
 *   created_at?: string,
 *   creator_name?: string,
 *   change_note?: string,
 * }} DatasetVersion
 *
 * @typedef {{
 *   id: string,
 *   mode: string,
 *   original_name: string,
 *   created_at?: string,
 *   row_count?: number,
 *   imported_row_count?: number,
 *   skipped_row_count?: number,
 *   creator_name?: string,
 *   change_note?: string,
 *   resulting_version_id?: string,
 * }} DatasetImport
 *
 * @typedef {{
 *   id: string,
 *   name: string,
 *   kind: string,
 *   source_key?: string,
 *   source_name?: string,
 *   version_id?: string,
 *   current_version: number,
 *   row_count: number,
 *   original_name?: string,
 *   creator_name?: string,
 *   updated_at?: string,
 *   quality?: DatasetQuality,
 *   versions?: DatasetVersion[],
 *   imports?: DatasetImport[],
 *   task_reference_count?: number,
 *   member_ids?: string[],
 *   schema?: unknown[],
 *   column_count?: number,
 *   audit?: DatasetAuditEntry[],
 * }} DatasetRecord
 * @typedef {DatasetRecord & {member_ids: string[]}} DatasetSource
 *
 * @typedef {{values?: Record<string, string | number | null>, items?: unknown[], store?: string, note?: string, row_index?: number}} DatasetAuditSide
 * @typedef {{id: string, action: string, actor_name?: string, created_at?: string, before?: DatasetAuditSide, after?: DatasetAuditSide}} DatasetAuditEntry
 *
 * @typedef {{
 *   task_id: string,
 *   reference_type: string,
 *   title?: string,
 *   status?: string,
 *   owner?: {name?: string},
 *   created_at?: string,
 *   version_snapshot?: Record<string, unknown>,
 * }} DatasetReference
 * @typedef {{items: DatasetReference[], total: number, version?: {name?: string, version?: number}}} DatasetReferencePage
 *
 * @typedef {{
 *   id: string,
 *   status?: string,
 *   name: string,
 *   kind?: string,
 *   version?: number,
 *   file_extensions?: string[],
 *   worksheet?: string,
 *   required_columns?: string[],
 *   optional_columns?: string[],
 *   match_key?: string[],
 *   notes?: string | string[],
 *   content_hash?: string,
 *   source?: string,
 * }} ImportRule
 * @typedef {{items: ImportRule[]}} ImportRulePage
 *
 * @typedef {{
 *   _row_index: number,
 *   MSKU: string,
 *   "店铺/站点": string,
 *   Listing: string,
 *   "产品名称"?: string,
 *   "品类A"?: string,
 *   "品类B"?: string,
 * } & Record<string, unknown>} DatasetRow
 * @typedef {{
 *   records: DatasetRow[],
 *   total: number,
 *   source_total?: number,
 *   facets?: {stores?: string[], categories?: string[]},
 * }} DatasetRowsPage
 *
 * @typedef {{
 *   version_count: number,
 *   physical_bytes: number,
 *   task_referenced_versions: number,
 *   dedup_reclaimable_bytes: number,
 *   expired_versions: number,
 *   retention_days: number,
 *   retain_latest: number,
 *   can_cleanup: boolean,
 * }} DatasetStorageSummary
 * @typedef {{after: DatasetStorageSummary, freed_bytes: number}} DatasetStorageCleanup
 */

export {};
