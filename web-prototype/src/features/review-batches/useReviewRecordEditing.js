import { useEffect, useState } from "react";
import { reviewBatchApi } from "../../shared/api/reviewBatchApi";
import { defaultReviewAssessment, reviewAssessment } from "./reviewAssessment";
import {
  itemId,
  semanticItemReviewDrafts,
  addedSemanticItemDrafts,
  requestError,
} from "./reviewRecordDrafts";

/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewAction} ReviewAction */
/** @typedef {import("./semanticLedgerContracts").AddedSemanticItem} AddedSemanticItem */
/** @typedef {import("./semanticLedgerContracts").CoverageStatus} CoverageStatus */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewConflict} ReviewConflict */
/** @typedef {import("./semanticLedgerContracts").ReviewRecord} ReviewRecord */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewRequestError} ReviewRequestError */
/** @typedef {import("./semanticLedgerContracts").SemanticItemReview} SemanticItemReview */

/** @param {import("./reviewWorkspaceContracts").ReviewEditingInput} input */
export function useReviewRecordEditing({
  route,
  notify,
  recordItems,
  recordQuery,
  loadBatch,
  loadRecords,
  setBatchState,
  setRecordsState,
}) {
  const [selected, setSelected] = useState(/** @type {ReviewRecord | null} */ (null));
  const [mode, setMode] = useState(/** @type {ReviewAction} */ ("confirm"));
  const [labelCode, setLabelCode] = useState("");
  const [reason, setReason] = useState("");
  const [assessment, setAssessment] = useState(() =>
    defaultReviewAssessment("confirm"),
  );
  const [semanticItemReviews, setSemanticItemReviews] = useState(
    /** @type {SemanticItemReview[]} */ ([]),
  );
  const [addedSemanticItems, setAddedSemanticItems] = useState(
    /** @type {AddedSemanticItem[]} */ ([]),
  );
  const [coverageStatus, setCoverageStatus] = useState(
    /** @type {CoverageStatus} */ ("complete"),
  );
  const [saving, setSaving] = useState(false);
  const [conflict, setConflict] = useState(/** @type {ReviewConflict | null} */ (null));
  useEffect(() => {
    setSelected(null);
    setConflict(null);
  }, [route.batchId]);

  /** @param {ReviewRecord} record */
  const openRecord = (record) => {
    const currentCode =
      record.classification?.problem_label_codes?.[0] ||
      record.classification?.positive_label_codes?.[0] ||
      "";
    setSelected(record);
    setMode("confirm");
    setLabelCode(currentCode);
    setReason("");
    setAssessment(reviewAssessment(record));
    setSemanticItemReviews(semanticItemReviewDrafts(record.classification));
    setAddedSemanticItems(addedSemanticItemDrafts(record.classification));
    setCoverageStatus(record.classification?.coverage_review?.status || "complete");
    setConflict(null);
  };

  /** @param {"confirm" | "modify" | "exclude"} nextMode */
  const changeMode = (nextMode) => {
    setMode(nextMode);
    setAssessment(defaultReviewAssessment(nextMode));
  };

  /** @param {ReviewRequestError} error */
  const refreshConflict = async (error) => {
    if (!selected) return;
    const selectedId = itemId(selected);
    const [latestBatch, latestPage] = await Promise.all([
      reviewBatchApi.reviewBatch(route.batchId),
      reviewBatchApi.reviewBatchRecords(route.batchId, recordQuery),
    ]);
    setBatchState({ loading: false, error: null, data: latestBatch });
    setRecordsState({
      loading: false,
      error: null,
      data: latestPage,
      batchId: route.batchId,
    });
    const serverRecord = latestPage.items?.find((item) => itemId(item) === selectedId);
    setConflict({ message: error.message, serverRecord });
  };

  /** @param {boolean} advance @param {ReviewRecord | undefined} nextPending @param {import("../../shared/api/reviewBatchContracts").ReviewRecordPage} latestPage @param {ReviewRecord} value */
  const selectSavedRecord = (advance, nextPending, latestPage, value) => {
    if (advance && nextPending) {
      openRecord(nextPending);
    } else if (advance) {
      setSelected(null);
    } else {
      const latestRecord = latestPage.items?.find(
        (item) => itemId(item) === itemId(value),
      );
      setSelected(latestRecord || null);
    }
  };
  const saveRecord = async (advance = false) => {
    if (!selected || !reason.trim()) return;
    const currentItems = recordItems;
    const currentIndex = currentItems.findIndex(
      (item) => itemId(item) === itemId(selected),
    );
    const nextPending = [
      ...currentItems.slice(currentIndex + 1),
      ...currentItems.slice(0, Math.max(currentIndex, 0)),
    ].find((item) => item.workflow_status === "pending");
    setSaving(true);
    try {
      const value = await reviewBatchApi.updateReviewBatchRecord(
        route.batchId,
        itemId(selected),
        {
          expected_revision: selected.revision,
          action: mode,
          label_code: mode === "modify" ? labelCode || null : null,
          reason: reason.trim(),
          label_correctness: assessment.labelCorrectness,
          evidence_completeness: assessment.evidenceCompleteness,
          review_routing: assessment.reviewRouting,
          semantic_item_reviews: semanticItemReviews,
          added_semantic_items: addedSemanticItems,
          coverage_status: coverageStatus,
        },
      );
      setReason("");
      setConflict(null);
      const [, latestPage] = await Promise.all([loadBatch(), loadRecords()]);
      selectSavedRecord(advance, nextPending, latestPage, value);
      const messages = {
        confirm: "已确认原分类结果",
        modify: "分类结果修改已保存",
        exclude: "该记录已排除，不再进入语义分析和看板",
      };
      notify(messages[mode]);
    } catch (error) {
      const failure = requestError(error);
      if (failure.status === 409) {
        try {
          await refreshConflict(failure);
        } catch (refreshError) {
          notify(requestError(refreshError).message, "error");
        }
      } else {
        notify(failure.message, "error");
      }
    } finally {
      setSaving(false);
    }
  };
  return {
    selected,
    setSelected,
    mode,
    labelCode,
    setLabelCode,
    reason,
    setReason,
    assessment,
    setAssessment,
    semanticItemReviews,
    setSemanticItemReviews,
    addedSemanticItems,
    setAddedSemanticItems,
    coverageStatus,
    setCoverageStatus,
    saving,
    conflict,
    setConflict,
    openRecord,
    changeMode,
    saveRecord,
  };
}
