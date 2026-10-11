/** @typedef {{route: import("../../shared/api/reviewBatchContracts").ReviewBatchRoute, updateRoute: (changes: Partial<import("../../shared/api/reviewBatchContracts").ReviewBatchRoute>) => void, notify: (message: string, type?: "success" | "error") => void, userId: string}} ReviewWorkspaceProps */
/** @typedef {Omit<ReviewWorkspaceProps, "userId"> & ReturnType<typeof import("./useReviewWorkspace").useReviewWorkspace>} ReviewWorkspaceContext */
export {};
