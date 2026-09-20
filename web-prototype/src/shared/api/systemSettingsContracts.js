/**
 * @typedef {"connection" | "limits" | "models" | "versions"} ActivePanel
 * @typedef {"create" | "edit"} ModelEditorMode
 * @typedef {"cheap_model" | "primary_model" | "secondary_model"} PipelineModelKey
 * @typedef {"cheap_effort" | "primary_effort" | "secondary_effort"} PipelineEffortKey
 * @typedef {"base_url" | "requests_per_minute" | "max_workers" | "timeout_seconds"} ConfigDiffKey
 *
 * @typedef {Object} ModelServiceForm
 * @property {string} name
 * @property {string} provider
 * @property {string} base_url
 * @property {string} api_key
 * @property {string} primary_model
 * @property {string} primary_effort
 * @property {string | null} cheap_model
 * @property {string} cheap_effort
 * @property {string | null} secondary_model
 * @property {string} secondary_effort
 * @property {number} cheap_audit_percent
 * @property {number} requests_per_minute
 * @property {number} max_workers
 * @property {number} timeout_seconds
 * @property {string} change_note
 * @property {string} [connection_id]
 *
 * @typedef {Object} CatalogModel
 * @property {string} id
 * @property {string} [connection_id]
 * @property {string} model_key
 * @property {string} display_name
 * @property {string[]} supported_efforts
 * @property {boolean} active
 * @property {string} validation_status
 * @property {string} [validation_message]
 * @property {string} [updater_name]
 * @property {string} [updated_at]
 * @property {boolean} [historical]
 * @typedef {{id: string, model_key: string, display_name: string, supported_efforts: string[], active: boolean, historical?: boolean}} ModelOption
 *
 * @typedef {Object} ModelDraft
 * @property {string} [id]
 * @property {string} model_key
 * @property {string} display_name
 * @property {string[]} supported_efforts
 * @property {boolean} active
 *
 * @typedef {Object} ConfigVersion
 * @property {string} id
 * @property {string} connection_id
 * @property {number} version
 * @property {string} base_url
 * @property {string} primary_model
 * @property {string} primary_effort
 * @property {string | null} cheap_model
 * @property {string} cheap_effort
 * @property {string | null} secondary_model
 * @property {string} secondary_effort
 * @property {number} cheap_audit_percent
 * @property {number} requests_per_minute
 * @property {number} max_workers
 * @property {number} timeout_seconds
 * @property {string} change_note
 * @property {string} validation_status
 * @property {string} [validation_message]
 * @property {string} [creator_name]
 * @property {string} created_at
 * @property {string | null} [validated_at]
 * @property {string | null} [published_at]
 *
 * @typedef {Object} ModelConnection
 * @property {string} id
 * @property {string} name
 * @property {string} provider
 * @property {string | null} active_version_id
 * @property {ConfigVersion[]} versions
 * @property {CatalogModel[]} models
 * @property {ConfigVersion | null} active_version
 *
 * @typedef {{model_id: string, model_key: string, display_name: string, role: string, effort: string, status: string, message: string, suggestion?: string, started_at?: string, duration_ms: number | null, http_status?: number}} ValidationItem
 * @typedef {Object} ValidationRun
 * @property {string} id
 * @property {string} status
 * @property {string} created_at
 * @property {string | null} started_at
 * @property {"config" | "model"} kind
 * @property {string} endpoint
 * @property {number} timeout_seconds
 * @property {string} creator_name
 * @property {number} completed_count
 * @property {number} total_count
 * @property {ValidationItem[]} [items]
 * @property {string} [error_message]
 * @property {string} [suggestion]
 * @property {string} [target_id]
 *
 * @typedef {{id: string | number, created_at: string, message: string}} ValidationEvent
 * @typedef {Array<[ConfigDiffKey, string]>} VersionChanges
 *
 * @typedef {{connection_id: string, cheap_model: string, cheap_effort: string, primary_model: string, primary_effort: string, secondary_model: string, secondary_effort: string, cheap_audit_percent: number}} ModelPreference
 *
 * @typedef {{route?: string, task_id?: string, segment_id?: string, result_version_id?: string, dashboard_id?: string, version_id?: string, report_id?: string, user_id?: string}} AuditTarget
 * @typedef {{id: string, actor_name?: string, action?: string, entity_type?: string, entity_id?: string, created_at?: string, target?: AuditTarget, before?: unknown, after?: unknown}} AuditLogEntry
 * @typedef {{items: AuditLogEntry[], total: number}} AuditLogPage
 *
 * @typedef {{id: string, action: string, before?: {active?: boolean}, after?: {active?: boolean, note?: string}, actor_name?: string, created_at?: string}} UserAuditEntry
 * @typedef {{id: string, display_name: string, email: string, active: boolean, audit?: UserAuditEntry[]}} TeamUser
 * @typedef {{id: string, email: string, expires_at: string, created_by: string, created_at: string}} TeamInvitation
 */

export {};
