import { useEffect, useState } from "react";
import Button from "antd/es/button";
import Checkbox from "antd/es/checkbox";
import { ArrowLeft, ListChecks } from "@phosphor-icons/react";

import { navigateHash } from "../../app/hashRouter";
import { Pagination } from "../../components/Pagination";
import { EmptyState, InlineLoading, PageLoadingState } from "../../components/SharedUi";
import { reviewBatchApi } from "../../shared/api/reviewBatchApi";
import {
  createDashboardSelection,
  selectionItem,
} from "../analysis-dashboards/dashboardSelectionStorage";
import { ReviewBulkDialog, ReviewPublishDialog } from "./ReviewBatchDialogs";
import { ReviewBatchError } from "./ReviewBatchError";
import { pendingCount } from "./reviewBatchPresentation";
import { resultRouteQuery } from "./reviewBatchRoute";
import {
  ReviewBatchSummary,
  ReviewBulkToolbar,
  ReviewRecordFilters,
} from "./ReviewBatchWorkspaceSections";
import { ReviewRecordDrawer, ReviewRecordRow } from "./ReviewRecordComponents";
import { defaultReviewAssessment, reviewAssessment } from "./reviewAssessment";
import { useReviewBatchData } from "./useReviewBatchData";

/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewAction} ReviewAction */
/** @typedef {import("../../shared/api/reviewBatchContracts").AddedSemanticItem} AddedSemanticItem */
/** @typedef {import("../../shared/api/reviewBatchContracts").ClassificationData} ClassificationData */
/** @typedef {import("../../shared/api/reviewBatchContracts").CoverageStatus} CoverageStatus */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewBatchRoute} ReviewBatchRoute */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewConflict} ReviewConflict */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewRecord} ReviewRecord */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewRequestError} ReviewRequestError */
/** @typedef {import("../../shared/api/reviewBatchContracts").SemanticItemReview} SemanticItemReview */

/** @param {ReviewRecord} item */
function itemId(item) {
  return item.id;
}

/** @param {ClassificationData | undefined} classification @returns {SemanticItemReview[]} */
function semanticItemReviewDrafts(classification) {
  return (classification?.human_semantic_reviews ?? []).map((item) => ({
    semantic_item_id: item.semantic_item_id,
    action: item.action,
    label_code: item.label_code ?? null,
    note: item.note ?? null,
  }));
}

/** @param {ClassificationData | undefined} classification @returns {AddedSemanticItem[]} */
function addedSemanticItemDrafts(classification) {
  return (classification?.human_added_semantic_items ?? []).map((item) => ({
    item_id: item.item_id,
    evidence_text: item.evidence_text,
    opinion: item.opinion,
    label_code: item.label_code,
    note: item.note ?? null,
  }));
}

/** @param {unknown} error @returns {ReviewRequestError} */
function requestError(error) {
  return error instanceof Error
    ? /** @type {ReviewRequestError} */ (error)
    : /** @type {ReviewRequestError} */ (new Error("复核操作失败"));
}

/**
 * @param {{route: ReviewBatchRoute, updateRoute: (changes: Partial<ReviewBatchRoute>) => void, notify: (message: string, type?: "success" | "error") => void, userId: string}} props
 */
export function ReviewBatchWorkspace({ route, updateRoute, notify, userId }) {
  const {
    batchState,
    recordsState,
    labels,
    recordQuery,
    loadBatch,
    loadRecords,
    setBatchState,
    setRecordsState,
  } = useReviewBatchData({ route, notify });
  const [filters, setFilters] = useState({
    q: route.q,
    status: route.status,
    listing: route.listing,
    productName: route.productName,
    productSku: route.productSku,
    orderId: route.orderId,
  });
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
  const [checkedIds, setCheckedIds] = useState(/** @type {string[]} */ ([]));
  const [bulkAction, setBulkAction] = useState(/** @type {ReviewAction | ""} */ (""));
  const [bulkLabelCode, setBulkLabelCode] = useState("");
  const [bulkReason, setBulkReason] = useState("");
  const [bulkSaving, setBulkSaving] = useState(false);
  const [bulkError, setBulkError] = useState("");
  const [conflict, setConflict] = useState(/** @type {ReviewConflict | null} */ (null));
  const [publishOpen, setPublishOpen] = useState(false);
  const [publishReason, setPublishReason] = useState("");
  const [publishError, setPublishError] = useState("");
  const [publishing, setPublishing] = useState(false);

  useEffect(() => {
    setFilters({
      q: route.q,
      status: route.status,
      listing: route.listing,
      productName: route.productName,
      productSku: route.productSku,
      orderId: route.orderId,
    });
  }, [
    route.listing,
    route.orderId,
    route.productName,
    route.productSku,
    route.q,
    route.status,
  ]);

  useEffect(() => {
    setSelected(null);
    setConflict(null);
    setCheckedIds([]);
  }, [route.batchId]);

  useEffect(() => {
    setCheckedIds([]);
  }, [recordQuery]);

  const batch = batchState.data?.id === route.batchId ? batchState.data : null;
  const records = recordsState.batchId === route.batchId ? recordsState.data : null;
  const recordItems = records?.items ?? [];
  const pending = pendingCount(batch);
  const readOnly = batch?.status === "published";

  const returnToList = () =>
    updateRoute({
      batchId: "",
      status: "",
      page: 1,
      listing: "",
      productName: "",
      productSku: "",
      orderId: "",
      q: "",
    });

  const openDerivedVersion = () => {
    if (!batch?.derived_result_version_id) return;
    navigateHash(
      "classification-results",
      resultRouteQuery(route, batch.derived_result_version_id),
    );
  };

  const createDashboardFromDerived = () => {
    if (!batch?.derived_result_version_id) return;
    const token = createDashboardSelection(userId, {
      selected: [
        selectionItem({
          version_id: batch.derived_result_version_id,
          version: batch.derived_version_no,
          result_state: "review-derived",
          quality_status: batch.derived_quality_status || "ready",
          store_site: batch.store_site,
          listing: batch.listing,
          record_count: batch.base_record_count || batch.record_count,
          unit_count: batch.base_unit_count || batch.unit_count,
          published_at: batch.derived_published_at,
        }),
      ],
    });
    navigateHash("analysis-dashboards", { selection_token: token, step: "check" });
  };
  const totalPages = Math.max(
    Math.ceil(Number(records?.total || 0) / route.pageSize),
    1,
  );

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

  const publish = async () => {
    if (!batch || pending > 0 || !publishReason.trim()) return;
    setPublishing(true);
    setPublishError("");
    try {
      const derived = await reviewBatchApi.publishReviewBatch(route.batchId, {
        expected_revision: batch.revision,
        reason: publishReason.trim(),
      });
      setPublishOpen(false);
      notify(`分类结果 v${derived.version} 已发布`);
      navigateHash(
        "classification-results",
        resultRouteQuery(route, derived.version_id, "history"),
      );
    } catch (error) {
      const failure = requestError(error);
      if (failure.status === 409) {
        setPublishError(`${failure.message}。已刷新批次，请重新确认后发布。`);
        try {
          await loadBatch();
        } catch {
          // 批次读取错误已由页面状态展示。
        }
      } else {
        setPublishError(failure.message);
      }
    } finally {
      setPublishing(false);
    }
  };

  if (!batch && (batchState.loading || batchState.data)) {
    return (
      <div className="standard-page review-batch-page review-batch-stable-state">
        <Button
          className="review-batch-back"
          type="text"
          icon={<ArrowLeft size={17} />}
          onClick={returnToList}
        >
          返回复核批次列表
        </Button>
        <PageLoadingState label="正在读取复核批次…" />
      </div>
    );
  }

  if (batchState.error && !batch) {
    return (
      <div className="standard-page review-batch-page review-batch-stable-state">
        <Button
          className="review-batch-back"
          type="text"
          icon={<ArrowLeft size={17} />}
          onClick={returnToList}
        >
          返回复核批次列表
        </Button>
        <ReviewBatchError error={batchState.error} onRetry={loadBatch} />
      </div>
    );
  }

  if (!batch) return null;

  return (
    <div className="standard-page review-batch-page">
      <ReviewBatchSummary
        batch={batch}
        pending={pending}
        readOnly={readOnly}
        onBack={returnToList}
        onOpenSource={() =>
          navigateHash(
            "classification-results",
            resultRouteQuery(route, batch.base_result_version_id, "history"),
          )
        }
        onOpenDerived={openDerivedVersion}
        onCreateDashboard={createDashboardFromDerived}
        onOpenPublish={() => {
          setPublishReason("");
          setPublishError("");
          setPublishOpen(true);
        }}
      />

      <ReviewRecordFilters
        filters={filters}
        onFilters={setFilters}
        onApply={() => updateRoute({ ...filters, page: 1 })}
      />

      {!readOnly && (
        <ReviewBulkToolbar
          checkedCount={checkedIds.length}
          onBulk={openBulk}
          onClear={() => setCheckedIds([])}
        />
      )}

      <section className="review-record-card">
        {recordsState.loading && !records && (
          <InlineLoading label="正在读取复核记录…" />
        )}
        {recordsState.error && (
          <ReviewBatchError error={recordsState.error} onRetry={loadRecords} />
        )}
        {!recordsState.loading && !recordsState.error && recordItems.length === 0 && (
          <EmptyState
            icon={ListChecks}
            title="当前条件没有复核记录"
            description="调整处理状态或业务字段后重新查询。"
          />
        )}
        {recordItems.length > 0 && !recordsState.error && (
          <>
            <div
              className={`review-record-table ${!readOnly ? "is-selectable" : ""} ${recordsState.loading ? "is-loading" : ""}`}
            >
              <div className="review-record-table-head" role="row">
                {!readOnly && (
                  <span className="review-record-checkbox">
                    <Checkbox
                      aria-label="选择本页待处理记录"
                      checked={
                        recordItems.some(
                          (record) => record.workflow_status === "pending",
                        ) &&
                        recordItems
                          .filter((record) => record.workflow_status === "pending")
                          .every((record) => checkedIds.includes(itemId(record)))
                      }
                      onChange={(event) => {
                        const pageIds = recordItems
                          .filter((record) => record.workflow_status === "pending")
                          .map(itemId);
                        setCheckedIds(event.target.checked ? pageIds : []);
                      }}
                    />
                  </span>
                )}
                <span>order-id / 产品名称</span>
                <span>Listing / 产品SKU</span>
                <span>退货SKU（MSKU）</span>
                <span>分类结果</span>
                <span>状态 / 操作</span>
              </div>
              {recordItems.map((record) => (
                <ReviewRecordRow
                  key={itemId(record)}
                  record={record}
                  selectionEnabled={!readOnly}
                  selectable={!readOnly && record.workflow_status === "pending"}
                  checked={checkedIds.includes(itemId(record))}
                  onCheck={(/** @type {boolean} */ checked) =>
                    setCheckedIds((current) =>
                      checked
                        ? [...current, itemId(record)]
                        : current.filter((id) => id !== itemId(record)),
                    )
                  }
                  onOpen={() => openRecord(record)}
                />
              ))}
            </div>
            <Pagination
              page={route.page}
              pageSize={route.pageSize}
              total={records?.total ?? 0}
              totalPages={totalPages}
              onPage={(/** @type {number} */ page) => updateRoute({ page })}
              onPageSize={(/** @type {number} */ pageSize) =>
                updateRoute({ page: 1, pageSize })
              }
            />
          </>
        )}
      </section>

      {selected && (
        <ReviewRecordDrawer
          record={selected}
          readOnly={readOnly}
          labels={labels}
          mode={mode}
          labelCode={labelCode}
          reason={reason}
          conflict={conflict}
          saving={saving}
          assessment={assessment}
          semanticItemReviews={semanticItemReviews}
          addedSemanticItems={addedSemanticItems}
          coverageStatus={coverageStatus}
          onMode={changeMode}
          onAssessment={setAssessment}
          onSemanticItemReviews={setSemanticItemReviews}
          onAddedSemanticItems={setAddedSemanticItems}
          onCoverageStatus={setCoverageStatus}
          onLabelCode={setLabelCode}
          onReason={setReason}
          onSave={() => saveRecord(false)}
          onSaveAndNext={() => saveRecord(true)}
          onClose={() => setSelected(null)}
          onUseServer={() => {
            if (!conflict?.serverRecord) return;
            openRecord(conflict.serverRecord);
          }}
          onContinueWithServer={() => {
            if (!conflict?.serverRecord) return;
            setSelected(conflict.serverRecord);
            setConflict(null);
          }}
        />
      )}

      <ReviewPublishDialog
        open={publishOpen}
        batch={batch}
        reason={publishReason}
        error={publishError}
        publishing={publishing}
        onReason={setPublishReason}
        onClose={() => setPublishOpen(false)}
        onPublish={publish}
      />

      <ReviewBulkDialog
        action={bulkAction}
        checkedCount={checkedIds.length}
        labels={labels}
        labelCode={bulkLabelCode}
        reason={bulkReason}
        error={bulkError}
        saving={bulkSaving}
        onLabelCode={setBulkLabelCode}
        onReason={setBulkReason}
        onClose={() => setBulkAction("")}
        onSave={saveBulk}
      />
    </div>
  );
}
