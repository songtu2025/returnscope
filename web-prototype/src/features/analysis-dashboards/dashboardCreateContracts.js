/** @typedef {import("./analysisDashboardContracts").DashboardSelectionItem} DashboardSelectionItem */
/** @typedef {import("./analysisDashboardContracts").DashboardSelection} DashboardSelection */

/**
 * @typedef {Object} DashboardConflict
 * @property {string} [conflict_id]
 * @property {string} [key]
 * @property {string} [store_site]
 * @property {string} [listing]
 * @property {string[]} [result_version_ids]
 */

/** @typedef {{type?: string, message?: string}} DashboardNotice */

/**
 * @typedef {Object} DashboardPlan
 * @property {string} plan_hash
 * @property {boolean} ready
 * @property {Record<string, string | string[] | null>} [filters]
 * @property {DashboardConflict[]} [conflicts]
 * @property {DashboardNotice[]} [blockers]
 * @property {DashboardNotice[]} [warnings]
 * @property {DashboardSelectionItem[]} [sources]
 * @property {import("./analysisDashboardContracts").InsightSummary} [summary]
 */

/**
 * @typedef {Object} DashboardCreateResponse
 * @property {string} [id]
 * @property {string} [dashboard_id]
 * @property {string} [current_version_id]
 * @property {string} [version_id]
 * @property {DashboardCreateResponse} [dashboard]
 * @property {DashboardCreateResponse} [version]
 * @property {DashboardCreateResponse} [current_version]
 */

/**
 * @typedef {Object} DashboardCreateRoute
 * @property {string} selectionToken
 * @property {"check" | "conflicts" | "confirm"} step
 */

/**
 * @typedef {Object} DashboardCreateProps
 * @property {DashboardCreateRoute} route
 * @property {(changes: Record<string, string | number>, options?: {replace?: boolean}) => void} updateRoute
 * @property {(message: string) => void} notify
 * @property {string} userId
 */

/** @typedef {DashboardCreateProps & ReturnType<typeof import("./useDashboardCreation").useDashboardCreation>} DashboardCreateContext */
export {};
