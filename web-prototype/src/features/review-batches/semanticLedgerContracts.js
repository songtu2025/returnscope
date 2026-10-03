/**
 * @typedef {import("../../shared/api/reviewBatchContracts").AddedSemanticItem} AddedSemanticItem
 * @typedef {import("../../shared/api/reviewBatchContracts").CoverageStatus} CoverageStatus
 * @typedef {import("../../shared/api/reviewBatchContracts").ReviewLabel} ReviewLabel
 * @typedef {import("../../shared/api/reviewBatchContracts").ReviewRecord} ReviewRecord
 * @typedef {import("../../shared/api/reviewBatchContracts").SemanticItemReview} SemanticItemReview
 * @typedef {import("../../shared/api/reviewBatchContracts").SemanticReviewAction} SemanticReviewAction
 * @typedef {import("../../shared/api/reviewBatchContracts").SemanticReviewLedgerItem} SemanticReviewLedgerItem
 */

/** @typedef {{record: ReviewRecord, labels: ReviewLabel[], editable: boolean, itemReviews: SemanticItemReview[], addedItems: AddedSemanticItem[], coverageStatus: CoverageStatus, onItemReviews: (value: SemanticItemReview[]) => void, onAddedItems: (value: AddedSemanticItem[]) => void, onCoverageStatus: (value: CoverageStatus) => void}} SemanticLedgerProps */
/** @typedef {SemanticLedgerProps & ReturnType<typeof import("./useSemanticLedger").useSemanticLedger>} SemanticLedgerContext */
export {};
