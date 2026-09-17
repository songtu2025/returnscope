/**
 * @typedef {Object} TaskModelPolicy
 * @property {string} connection_id
 * @property {string} cheap_model
 * @property {string} cheap_effort
 * @property {string} primary_model
 * @property {string} primary_effort
 * @property {string} secondary_model
 * @property {string} secondary_effort
 * @property {number} cheap_audit_percent
 *
 * @typedef {Object} TaskForm
 * @property {string} title
 * @property {string} dataset_version_id
 * @property {string} product_version_id
 * @property {string} config_version_id
 * @property {string} store
 * @property {string} listing
 * @property {TaskModelPolicy} [model_policy]
 *
 * @typedef {Object} DataVersion
 * @property {string} version_id
 * @property {string} dataset_id
 * @property {string} dataset_name
 * @property {"returns" | "products" | string} kind
 * @property {number} version
 * @property {number} current_version
 * @property {number} row_count
 * @property {string} [source_key]
 * @property {string} [source_name]
 * @property {string} [usage_scope]
 * @property {{stores?: string[], valid_comment_rows?: number, missing_store_rows?: number} & Record<string, unknown>} [quality]
 *
 * @typedef {Object} AvailableModel
 * @property {string} id
 * @property {string} model_key
 * @property {string} display_name
 * @property {string[]} supported_efforts
 * @property {boolean} active
 * @property {string} validation_status
 *
 * @typedef {Object} ApiConfigVersion
 * @property {string} id
 * @property {string} connection_id
 * @property {string | number} version
 * @property {string} primary_model
 * @property {string} [primary_effort]
 * @property {string | null} [cheap_model]
 * @property {string} [cheap_effort]
 * @property {string | null} [secondary_model]
 * @property {string} [secondary_effort]
 * @property {number} [cheap_audit_percent]
 *
 * @typedef {ApiConfigVersion & {connection_name: string}} PublishedConfig
 *
 * @typedef {Object} ApiConnection
 * @property {string} id
 * @property {string} name
 * @property {ApiConfigVersion | null} [active_version]
 * @property {AvailableModel[]} [models]
 *
 * @typedef {Object} ModelPreference
 * @property {string} config_version_id
 * @property {string} connection_id
 * @property {string} cheap_model
 * @property {string} cheap_effort
 * @property {string} primary_model
 * @property {string} primary_effort
 * @property {string} secondary_model
 * @property {string} secondary_effort
 * @property {number} [cheap_audit_percent]
 *
 * @typedef {Object} TaskSystemStatus
 * @property {number} [my_running_tasks]
 *
 * @typedef {Object} TaskDraft
 * @property {number} [step]
 * @property {boolean} [resumePreflight]
 * @property {"existing" | "upload" | "mysql"} [dataEntryMode]
 * @property {string} [selectedDataLabel]
 * @property {Partial<import("./MysqlReturnImportForm").MysqlReturnFormState>} [mysqlDraft]
 * @property {Partial<TaskForm>} [form]
 * @property {TaskRepairContext | null} [repairContext]
 *
 * @typedef {Object} TaskRepairContext
 * @property {"dataset"} kind
 * @property {string} [id]
 * @property {string} datasetKind
 * @property {boolean} [returnToTask]
 * @property {string} [taskTitle]
 * @property {string} [store]
 * @property {UnresolvedProduct[]} [unresolvedProducts]
 * @property {CategoryOption[]} [categoryOptions]
 * @property {number} [blockedCommentCount]
 *
 * @typedef {{category_a: string, category_b: string}} CategoryOption
 * @typedef {Object} UnresolvedProduct
 * @property {string} product_key
 * @property {string} [msku]
 * @property {string} [product_name]
 * @property {string} [suggested_listing]
 * @property {string} [issue]
 * @property {boolean} [editable]
 * @property {number} [comment_count]
 * @property {number} [record_count]
 *
 * @typedef {Object} TaskPreflightState
 * @property {"idle" | "loading" | "ready" | "error"} status
 * @property {import("../task-planning/taskPlanContracts").TaskExecutionPlan | null} data
 * @property {string} error
 *
 * @typedef {Object} TaskPlanViewState
 * @property {boolean} blocked
 * @property {boolean} canContinue
 * @property {boolean} categoryCompletionRequired
 * @property {boolean} countMismatch
 * @property {boolean} noExecutable
 * @property {boolean} partialPlan
 * @property {boolean} requiresScopeConfirmation
 *
 * @typedef {Object} MysqlFormState
 * @property {boolean} ready
 * @property {string} busy
 * @property {number} rowCount
 *
 * @typedef {Object} ReturnImportResult
 * @property {string} version_id
 * @property {boolean} [duplicate]
 * @property {"analyze_only" | "create" | "append" | "replace"} [mode]
 * @property {{imported_row_count?: number, skipped_row_count?: number}} [summary]
 * @property {{id: string}} [dataset]
 *
 * @typedef {Object} ReturnImportMatch
 * @property {string} dataset_id
 * @property {string} dataset_name
 * @property {number} row_count
 *
 * @typedef {Object} ReturnImportInspection
 * @property {string} inspection_id
 * @property {string} original_name
 * @property {string} suggested_name
 * @property {string[]} [stores]
 * @property {number} row_count
 * @property {{valid_comment_rows?: number, missing_store_rows?: number}} [quality]
 * @property {ReturnImportMatch[]} [matches]
 * @property {{dataset_name: string}} [duplicate]
 */

export {};
