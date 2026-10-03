/** @typedef {import("../analysis-dashboards/analysisDashboardContracts").DashboardSelectionItem} DashboardSelectionItem */
/** @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultVersionResponse} ClassificationResultVersion */
/** @typedef {import("./classificationResultRoute").ClassificationResultRoute} ClassificationResultRoute */
/** @typedef {import("../analysis-dashboards/analysisDashboardContracts").DashboardSelection} DashboardSelection */
/**
 * @typedef {object} InsightModel
 * @property {string} id
 * @property {string} [model_key]
 * @property {string} [display_name]
 * @property {string} [connection_id]
 * @property {string} [connection_name]
 * @property {string[]} [supported_efforts]
 */
/**
 * @typedef {object} InsightPlan
 * @property {boolean} ready
 * @property {string} plan_hash
 * @property {Record<string, string | string[] | null>} [filters]
 * @property {{ message: string }[]} [blockers]
 * @property {unknown[]} [conflicts]
 * @property {import("../analysis-dashboards/analysisDashboardContracts").DashboardSource[]} [sources]
 * @property {{ record_count?: number, pending_review_record_count?: number, excluded_record_count?: number }} [summary]
 */
/**
 * @typedef {object} InsightState
 * @property {boolean} loading
 * @property {boolean} submitting
 * @property {string} error
 * @property {InsightPlan | null} plan
 * @property {InsightModel[]} models
 */
/** @typedef {{ modelId: string, effort: string }} InsightForm */
/**
 * @typedef {object} ClassificationResultListProps
 * @property {ClassificationResultRoute} route
 * @property {(changes: Partial<ClassificationResultRoute>) => void} updateRoute
 * @property {(message: string, tone?: string) => void} notify
 * @property {string} userId
 */

/** @typedef { ClassificationResultListProps & ReturnType<typeof import("./useResultPoolWorkspace").useResultPoolWorkspace>} ResultPoolContext */
export {};
