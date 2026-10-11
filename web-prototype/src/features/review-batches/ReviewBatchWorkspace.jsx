import Button from "antd/es/button";
import { ArrowLeft } from "@phosphor-icons/react";
import { navigateHash } from "../../app/hashRouter";
import { PageLoadingState } from "../../components/SharedUi";
import { ReviewBatchError } from "./ReviewBatchError";
import { resultRouteQuery } from "./reviewBatchRoute";
import {
  ReviewBatchSummary,
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
    returnToList,
    openDerivedVersion,
    selected,
    setSelected,
  } = context;

  if (!batch)
    return (
      <div className="standard-page review-batch-page review-batch-stable-state">
        <Button
          className="review-batch-back"
          type="text"
          icon={<ArrowLeft size={17} />}
          onClick={returnToList}
        >
          返回历史复核记录
        </Button>
        {batchState.error ? (
          <ReviewBatchError error={batchState.error} onRetry={loadBatch} />
        ) : (
          <PageLoadingState label="正在读取历史复核记录…" />
        )}
      </div>
    );

  return (
    <div className="standard-page review-batch-page">
      <ReviewBatchSummary
        batch={batch}
        pending={pending}
        onBack={returnToList}
        onOpenSource={() =>
          navigateHash(
            "classification-results",
            resultRouteQuery(route, batch.base_result_version_id, "history"),
          )
        }
        onOpenDerived={openDerivedVersion}
      />
      <ReviewRecordFilters
        filters={filters}
        onFilters={setFilters}
        onApply={() => updateRoute({ ...filters, page: 1 })}
      />
      <ReviewRecordTable {...context} />
      {selected && (
        <ReviewRecordDrawer
          record={selected}
          labels={labels}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
