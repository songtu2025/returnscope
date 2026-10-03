import Button from "antd/es/button";
import { ArrowLeft } from "@phosphor-icons/react";
import { navigateHash } from "../../app/hashRouter";
import { PageLoadingState } from "../../components/SharedUi";
import { ReviewBulkDialog, ReviewPublishDialog } from "./ReviewBatchDialogs";
import { ReviewBatchError } from "./ReviewBatchError";
import { resultRouteQuery } from "./reviewBatchRoute";
import {
  ReviewBatchSummary,
  ReviewBulkToolbar,
  ReviewRecordFilters,
} from "./ReviewBatchWorkspaceSections";
import { ReviewRecordDrawer } from "./ReviewRecordComponents";
import { useReviewWorkspace } from "./useReviewWorkspace";
import { ReviewRecordTable } from "./ReviewRecordTable";

/** @param {import("./reviewWorkspaceContracts").ReviewWorkspaceProps} props */
export function ReviewBatchWorkspace(props) {
  const context = useReviewWorkspace(props);
  const {
    route,
    updateRoute,
    batchState,
    labels,
    loadBatch,
    filters,
    setFilters,
    batch,
    pending,
    readOnly,
    returnToList,
    openDerivedVersion,
    createDashboardFromDerived,
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
    publishOpen,
    setPublishOpen,
    publishReason,
    setPublishReason,
    publishError,
    setPublishError,
    publishing,
    publish,
  } = context;

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

      <ReviewRecordTable {...context} />

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
