/** @typedef {import("../../app/navigation").Navigate} Navigate */
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRecord} DatasetRecord */
/** @typedef {import("../task-create/taskCreateContracts").TaskDraft} TaskDraft */
/** @typedef {import("../task-create/taskCreateContracts").TaskRepairContext} TaskRepairContext */
/** @typedef {{mode: "create", kind: string} | {mode: "update", dataset: DatasetRecord}} UploadDialog */

/**
 * @typedef {{
 *   notify: (message: string, tone?: string) => void,
 *   onNavigate: Navigate,
 *   returnPosition?: import("react").MutableRefObject<import("../../hooks/useListReturnPosition").ListReturnPosition | null>,
 *   focus?: TaskRepairContext | null,
 *   taskDraft?: TaskDraft | null,
 *   onReturnToTask?: (productVersionId: string) => void,
 *   onReturnResult?: () => void,
 *   routeDetailTab?: string,
 *   onDetailTabChange?: (tab: string) => void,
 *   routeReferencePage?: string | number,
 *   onReferenceRouteChange?: (changes: Record<string, string | number>) => void,
 *   onAssetViewChange?: (view: string) => void,
 * }} ProductMasterProps
 */

export {};
