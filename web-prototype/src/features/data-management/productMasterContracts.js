/** @typedef {import("../../app/navigation").Navigate} Navigate */
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRecord} DatasetRecord */
/** @typedef {import("../task-create/taskCreateContracts").TaskDraft} TaskDraft */
/** @typedef {import("../task-create/taskCreateContracts").TaskRepairContext} TaskRepairContext */
/** @typedef {{mode: "create", kind: string} | {mode: "version", dataset: DatasetRecord}} UploadDialog */

/**
 * @typedef {{
 *   notify: (message: string, tone?: string) => void,
 *   onNavigate: Navigate,
 *   focus?: TaskRepairContext | null,
 *   taskDraft?: TaskDraft | null,
 *   onReturnToTask?: (productVersionId: string) => void,
 *   routeDetailTab?: string,
 *   onDetailTabChange?: (tab: string) => void,
 *   routeReferenceVersion?: string,
 *   routeReferencePage?: string | number,
 *   onReferenceRouteChange?: (changes: Record<string, string | number>) => void,
 *   onAssetViewChange?: (view: string) => void,
 * }} ProductMasterProps
 */

export {};
