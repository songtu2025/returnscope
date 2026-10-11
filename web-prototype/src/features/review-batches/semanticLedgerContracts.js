/**
 * @typedef {import("../../shared/api/reviewBatchContracts").AddedSemanticItem} AddedSemanticItem
 * @typedef {import("../../shared/api/reviewBatchContracts").CoverageStatus} CoverageStatus
 * @typedef {import("../../shared/api/reviewBatchContracts").ReviewLabel} ReviewLabel
 * @typedef {import("../../shared/api/reviewBatchContracts").ReviewRecord} ReviewRecord
 * @typedef {import("../../shared/api/reviewBatchContracts").SemanticItemReview} SemanticItemReview
 * @typedef {import("../../shared/api/reviewBatchContracts").SemanticReviewAction} SemanticReviewAction
 * @typedef {import("../../shared/api/reviewBatchContracts").SemanticReviewLedgerItem} SemanticReviewLedgerItem
 */

/** @typedef {{record: ReviewRecord, labels: ReviewLabel[], itemReviews: SemanticItemReview[], addedItems: AddedSemanticItem[], coverageStatus: CoverageStatus}} SemanticLedgerProps */
/** @typedef {SemanticLedgerProps & ReturnType<typeof import("./useSemanticLedger").useSemanticLedger>} SemanticLedgerContext */
export {};
