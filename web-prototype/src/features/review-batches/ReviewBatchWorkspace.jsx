import { useEffect, useState } from "react";
import Checkbox from "antd/es/checkbox";
import { ListChecks } from "@phosphor-icons/react";

import { navigateHash } from "../../app/hashRouter";
import { Pagination } from "../../components/Pagination";
import { EmptyState, InlineLoading } from "../../components/SharedUi";
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

function itemId(item) {
  return item.id;
}

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
  const [selected, setSelected] = useState(null);
  const [mode, setMode] = useState("confirm");
  const [labelCode, setLabelCode] = useState("");
  const [reason, setReason] = useState("");
  const [assessment, setAssessment] = useState(() =>
    defaultReviewAssessment("confirm"),
  );
  const [saving, setSaving] = useState(false);
  const [checkedIds, setCheckedIds] = useState([]);
  const [bulkAction, setBulkAction] = useState("");
  const [bulkLabelCode, setBulkLabelCode] = useState("");
  const [bulkReason, setBulkReason] = useState("");
  const [bulkSaving, setBulkSaving] = useState(false);
  const [bulkError, setBulkError] = useState("");
  const [conflict, setConflict] = useState(null);
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

  const batch = batchState.data;
  const records = recordsState.data;
  const pending = pendingCount(batch);
  const readOnly = batch?.status === "published";

  const openDerivedVersion = () => {
    navigateHash(
      "classification-results",
      resultRouteQuery(route, batch.derived_result_version_id),
    );
  };

  const createDashboardFromDerived = () => {
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

  const openRecord = (record) => {
    const currentCode =
      record.classification?.primary_label_codes?.[0] ||
      record.classification?.problem_label_codes?.[0] ||
      "";
    setSelected(record);
    setMode("confirm");
    setLabelCode(currentCode);
    setReason("");
    setAssessment(reviewAssessment(record));
    setConflict(null);
  };

  /** @param {"confirm" | "modify" | "exclude"} nextMode */
  const changeMode = (nextMode) => {
    setMode(nextMode);
    setAssessment(defaultReviewAssessment(nextMode));
  };

  const refreshConflict = async (error) => {
    const [latestBatch, latestPage] = await Promise.all([
      reviewBatchApi.reviewBatch(route.batchId),
      reviewBatchApi.reviewBatchRecords(route.batchId, recordQuery),
    ]);
    setBatchState({ loading: false, error: null, data: latestBatch });
    setRecordsState({ loading: false, error: null, data: latestPage });
    const serverRecord = latestPage.items?.find(
      (item) => itemId(item) === itemId(selected),
    );
    setConflict({ message: error.message, serverRecord });
  };

  const saveRecord = async (advance = false) => {
    if (!selected || !reason.trim()) return;
    const currentItems = records?.items ?? [];
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
      if (error.status === 409) {
        try {
          await refreshConflict(error);
        } catch (refreshError) {
          notify(refreshError.message, "error");
        }
      } else {
        notify(error.message, "error");
      }
    } finally {
      setSaving(false);
    }
  };

  const openBulk = (action) => {
    setBulkAction(action);
    setBulkLabelCode("");
    setBulkReason("");
    setBulkError("");
  };

  const saveBulk = async () => {
    const selectedRecords = (records?.items ?? []).filter((record) =>
      checkedIds.includes(itemId(record)),
    );
    if (!selectedRecords.length || !bulkReason.trim()) return;
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
      setBulkError(error.message);
      if (error.status === 409) {
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
      if (error.status === 409) {
        setPublishError(`${error.message}。已刷新批次，请重新确认后发布。`);
        try {
          await loadBatch();
        } catch {
          // 批次读取错误已由页面状态展示。
        }
      } else {
        setPublishError(error.message);
      }
    } finally {
      setPublishing(false);
    }
  };

  if (batchState.loading && !batch) {
    return (
      <div className="standard-page review-batch-page review-batch-stable-state">
        <InlineLoading label="正在读取复核批次…" />
      </div>
    );
  }

  if (batchState.error && !batch) {
    return (
      <div className="standard-page review-batch-page review-batch-stable-state">
        <ReviewBatchError error={batchState.error} onRetry={loadBatch} />
      </div>
    );
  }

  return (
    <div className="standard-page review-batch-page">
      <ReviewBatchSummary
        batch={batch}
        pending={pending}
        readOnly={readOnly}
        onBack={() =>
          updateRoute({
            batchId: "",
            status: "",
            page: 1,
            listing: "",
            productName: "",
            productSku: "",
            orderId: "",
            q: "",
          })
        }
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
        {!recordsState.loading &&
          !recordsState.error &&
          records?.items?.length === 0 && (
            <EmptyState
              icon={ListChecks}
              title="当前条件没有复核记录"
              description="调整处理状态或业务字段后重新查询。"
            />
          )}
        {records?.items?.length > 0 && !recordsState.error && (
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
                        records.items.some(
                          (record) => record.workflow_status === "pending",
                        ) &&
                        records.items
                          .filter((record) => record.workflow_status === "pending")
                          .every((record) => checkedIds.includes(itemId(record)))
                      }
                      onChange={(event) => {
                        const pageIds = records.items
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
              {records.items.map((record) => (
                <ReviewRecordRow
                  key={itemId(record)}
                  record={record}
                  selectionEnabled={!readOnly}
                  selectable={!readOnly && record.workflow_status === "pending"}
                  checked={checkedIds.includes(itemId(record))}
                  onCheck={(checked) =>
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
              total={records.total}
              totalPages={totalPages}
              onPage={(page) => updateRoute({ page })}
              onPageSize={(pageSize) => updateRoute({ page: 1, pageSize })}
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
          onMode={changeMode}
          onAssessment={setAssessment}
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
