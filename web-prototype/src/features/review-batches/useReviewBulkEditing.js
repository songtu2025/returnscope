import { useEffect, useState } from "react";
import { reviewBatchApi } from "../../shared/api/reviewBatchApi";
import { itemId, requestError } from "./reviewRecordDrafts";

/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewAction} ReviewAction */

/** @param {import("./reviewWorkspaceContracts").ReviewEditingInput} input */
export function useReviewBulkEditing({
  route,
  notify,
  recordItems,
  recordQuery,
  loadBatch,
  loadRecords,
}) {
  const [checkedIds, setCheckedIds] = useState(/** @type {string[]} */ ([]));
  const [bulkAction, setBulkAction] = useState(/** @type {ReviewAction | ""} */ (""));
  const [bulkLabelCode, setBulkLabelCode] = useState("");
  const [bulkReason, setBulkReason] = useState("");
  const [bulkSaving, setBulkSaving] = useState(false);
  const [bulkError, setBulkError] = useState("");
  useEffect(() => {
    setCheckedIds([]);
  }, [route.batchId, recordQuery]);

  /** @param {ReviewAction} action */
  const openBulk = (action) => {
    setBulkAction(action);
    setBulkLabelCode("");
    setBulkReason("");
    setBulkError("");
  };

  const saveBulk = async () => {
    const selectedRecords = recordItems.filter((record) =>
      checkedIds.includes(itemId(record)),
    );
    if (!selectedRecords.length || !bulkReason.trim() || !bulkAction) return;
    setBulkSaving(true);
    setBulkError("");
    try {
      await reviewBatchApi.updateReviewBatchRecords(route.batchId, {
        records: selectedRecords.map((record) => ({
          id: itemId(record),
          expected_revision: record.revision,
        })),
        action: bulkAction,
        label_code: bulkAction === "modify" ? bulkLabelCode || null : null,
        reason: bulkReason.trim(),
      });
      setBulkAction("");
      setCheckedIds([]);
      await Promise.all([loadBatch(), loadRecords()]);
      notify(`已批量处理 ${selectedRecords.length} 条复核记录`);
    } catch (error) {
      const failure = requestError(error);
      setBulkError(failure.message);
      if (failure.status === 409) {
        await Promise.all([loadBatch(), loadRecords()]);
      }
    } finally {
      setBulkSaving(false);
    }
  };
  return {
    checkedIds,
    setCheckedIds,
    bulkAction,
    setBulkAction,
    bulkLabelCode,
    setBulkLabelCode,
    bulkReason,
    setBulkReason,
    bulkSaving,
    bulkError,
    openBulk,
    saveBulk,
  };
}
