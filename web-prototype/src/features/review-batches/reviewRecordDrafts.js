/** @typedef {import("./semanticLedgerContracts").AddedSemanticItem} AddedSemanticItem */
/** @typedef {import("../../shared/api/reviewBatchContracts").ClassificationData} ClassificationData */
/** @typedef {import("./semanticLedgerContracts").ReviewRecord} ReviewRecord */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewRequestError} ReviewRequestError */
/** @typedef {import("./semanticLedgerContracts").SemanticItemReview} SemanticItemReview */

/** @param {ReviewRecord} item */
export function itemId(item) {
  return item.id;
}

/** @param {ClassificationData | undefined} classification @returns {SemanticItemReview[]} */
export function semanticItemReviewDrafts(classification) {
  return (classification?.human_semantic_reviews ?? [])
    .filter((item) => !item.applied)
    .map((item) => ({
      semantic_item_id: item.semantic_item_id,
      action: item.action,
      label_code: item.label_code ?? null,
      note: item.note ?? null,
      ...(item.sentiment ? { sentiment: item.sentiment } : {}),
    }));
}

/** @param {ClassificationData | undefined} classification @returns {AddedSemanticItem[]} */
export function addedSemanticItemDrafts(classification) {
  return (classification?.human_added_semantic_items ?? [])
    .filter((item) => !item.applied)
    .map((item) => ({
      item_id: item.item_id,
      evidence_text: item.evidence_text,
      opinion: item.opinion,
      label_code: item.label_code,
      note: item.note ?? null,
      ...(item.sentiment ? { sentiment: item.sentiment } : {}),
    }));
}

/** @param {unknown} error @returns {ReviewRequestError} */
export function requestError(error) {
  return error instanceof Error
    ? /** @type {ReviewRequestError} */ (error)
    : /** @type {ReviewRequestError} */ (new Error("复核操作失败"));
}
