/** @typedef {import("./navigation").NavigationFocus} NavigationFocus */
/** @typedef {{id: string, email: string, display_name: string, is_admin?: boolean}} CurrentUser */
/** @typedef {{warnings?: string[], pending_review_batches?: number, pending_review_batch_count?: number, review_batch_pending_count?: number, my_running_segments?: number, my_running_tasks?: number}} SystemStatus */
/** @typedef {{message: string, tone: string}} ToastState */
/** @typedef {(message: string, tone?: string) => void} Notify */
/** @typedef {(destination: string, focus?: NavigationFocus | null) => void} Navigate */

export {};
