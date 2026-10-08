/** @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultVersionResponse} ClassificationResultVersion */
/** @typedef {import("./classificationResultRoute").ClassificationResultRoute} ClassificationResultRoute */
/** @typedef {import("../analysis-dashboards/analysisDashboardContracts").DashboardSelection} DashboardSelection */
/**
 * @typedef {object} ClassificationResultListProps
 * @property {ClassificationResultRoute} route
 * @property {(changes: Partial<ClassificationResultRoute>) => void} updateRoute
 * @property {(message: string, tone?: string) => void} notify
 * @property {string} userId
 */

/** @typedef { ClassificationResultListProps & ReturnType<typeof import("./useResultPoolWorkspace").useResultPoolWorkspace>} ResultPoolContext */
export {};
