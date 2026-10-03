/** @typedef {{route: import("../../shared/api/reviewBatchContracts").ReviewBatchRoute, updateRoute: (changes: Partial<import("../../shared/api/reviewBatchContracts").ReviewBatchRoute>) => void, notify: (message: string, type?: "success" | "error") => void, userId: string}} ReviewWorkspaceProps */
/** @typedef {ReviewWorkspaceProps & ReturnType<typeof import("./useReviewBatchData").useReviewBatchData> & {recordItems: import("../../shared/api/reviewBatchContracts").ReviewRecord[], batch: import("../../shared/api/reviewBatchContracts").ReviewBatch | null, pending: number}} ReviewEditingInput */
/** @typedef {ReviewWorkspaceProps & ReturnType<typeof import("./useReviewWorkspace").useReviewWorkspace>} ReviewWorkspaceContext */
export {};
