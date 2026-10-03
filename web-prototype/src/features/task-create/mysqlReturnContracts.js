/** @typedef {{ name: string, label: string, required?: boolean }} MysqlField */
/** @typedef {{ name: string, label?: string, type: string }} MysqlColumn */
/** @typedef {Record<string, string>} MysqlFieldMapping */
/**
 * @typedef {{
 *   configured: true,
 *   database: string,
 *   table: string,
 *   max_rows: number,
 *   fields: MysqlField[],
 *   columns: MysqlColumn[],
 *   mapping: MysqlFieldMapping,
 *   stores?: string[]
 * }} ConfiguredMysqlSchema
 */
/** @typedef {ConfiguredMysqlSchema | { configured: false }} MysqlSchema */
/** @typedef {Record<string, string | number | null | undefined>} MysqlPreviewRow */
/**
 * @typedef {{
 *   row_count: number,
 *   over_limit: boolean,
 *   missing_store_rows: number,
 *   rows: MysqlPreviewRow[]
 * }} MysqlPreview
 */
/**
 * @typedef {{
 *   mapping: MysqlFieldMapping,
 *   default_store: string,
 *   date_from: string,
 *   date_to: string,
 *   store: string,
 *   sku: string
 * }} MysqlReturnFormState
 */
/**
 * @typedef {Omit<MysqlReturnFormState, "date_from" | "date_to"> & {
 *   date_from: string | null,
 *   date_to: string | null
 * }} MysqlReturnRequest
 */
/** @typedef {{ version_id: string } & Record<string, unknown>} MysqlImportResult */
/** @typedef {{ ready: boolean, busy: string, rowCount: number }} MysqlFormState */
/**
 * @typedef {{
 *   onDone: (result: MysqlImportResult) => void | Promise<void>,
 *   draft?: Partial<MysqlReturnFormState>,
 *   onDraftChange?: (draft: MysqlReturnFormState) => void,
 *   onStateChange?: (state: MysqlFormState) => void,
 *   onInvalidate?: () => void,
 *   prepared?: boolean,
 *   disabled?: boolean
 * }} MysqlReturnImportFormProps
 */

export {};
