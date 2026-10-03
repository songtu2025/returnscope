import { ArrowLeft, ListChecks, WarningCircle } from "@phosphor-icons/react";
import { ResultVersionReviewPanel } from "../review-batches/ResultVersionReviewPanel";
import { EvidenceDrawer } from "./EvidenceDrawer";
import { resultDetailPresentation } from "./resultDetailPresentation";
import { resultDetailActions } from "./resultDetailActions";
import { ResultDetailHeader } from "./ResultDetailHeader";
import { ResultDetailMetrics } from "./ResultDetailMetrics";
import { ResultDetailDrilldown } from "./ResultDetailDrilldown";
import { ResultDetailRecords } from "./ResultDetailRecords";

/** @typedef {import("./classificationResultDetailContracts").ResultDetailViewProps} ResultDetailViewProps */

/** @param {ResultDetailViewProps} props */
export function ClassificationResultDetailView(props) {
  const presentation = resultDetailPresentation(props);
  const actions = resultDetailActions({ ...props, policy: presentation.policy });
  const context = { ...props, ...presentation, ...actions };
  const {
    route,
    updateRoute,
    notify,
    result,
    selectedGroup,
    closeEvidence,
    evidenceTriggerRef,
    reviewRecords,
    policy,
    allNeedReviewWithoutProblems,
    selectVersion,
  } = context;
  return (
    <div className="standard-page classification-results-page result-detail-page">
      <button
        className="text-button result-back-button"
        onClick={() =>
          updateRoute({
            version: "",
            recordPage: 1,
            problem: "",
            productName: "",
            productSku: "",
            orderId: "",
          })
        }
      >
        <ArrowLeft size={17} /> 返回分类结果池
      </button>

      <ResultDetailHeader {...context} />

      {policy.blockingReason && (
        <div className={`result-action-guidance is-${policy.state}`} role="status">
          <WarningCircle size={19} />
          <span>{policy.blockingReason}</span>
        </div>
      )}

      {allNeedReviewWithoutProblems && (
        <div className="result-action-guidance is-needs-review" role="status">
          <ListChecks size={19} />
          <span>
            尚未形成问题标签；当前{" "}
            {Number(reviewRecords || result.record_count).toLocaleString()}{" "}
            条均需复核，完成复核并发布派生版本后可按问题下钻。
          </span>
        </div>
      )}

      <nav className="result-detail-tabs" aria-label="分类结果详情">
        <button
          className={route.tab === "records" ? "active" : ""}
          onClick={() => updateRoute({ tab: "records" })}
        >
          分类数据
        </button>
        <button
          className={route.tab === "history" ? "active" : ""}
          onClick={() => updateRoute({ tab: "history" })}
        >
          版本历史与复核
        </button>
      </nav>

      {route.tab === "history" ? (
        <ResultVersionReviewPanel
          result={result}
          notify={notify}
          requestedAction={route.action}
          routeContext={{
            ...route,
            taskId: route.taskId || result.source_task_id,
            segmentId: route.segmentId || result.source_segment_id,
          }}
          onActionHandled={() => updateRoute({ action: "" })}
          onSelectVersion={selectVersion}
        />
      ) : (
        <>
          <ResultDetailMetrics {...context} />
          <ResultDetailAccounting {...context} />

          <ResultDetailDrilldown {...context} />

          <ResultDetailRecords {...context} />

          {selectedGroup && (
            <EvidenceDrawer
              group={selectedGroup}
              analysisContext={result.analysis_context}
              onClose={closeEvidence}
              returnFocusRef={evidenceTriggerRef}
            />
          )}
        </>
      )}
    </div>
  );
}

/** @param {import("./classificationResultDetailContracts").ResultDetailContext} context */
function ResultDetailAccounting(context) {
  const {
    readyRecords,
    reviewRecords,
    excludedRecords,
    unusableRecords,
    accountedRecords,
    totalRecords,
  } = context;
  return (
    <p
      className={`result-accounting-note ${accountedRecords === totalRecords ? "is-balanced" : "is-warning"}`}
      role="status"
    >
      记录对账：{totalRecords.toLocaleString()} ={" "}
      {Number(readyRecords || 0).toLocaleString()} 可用 +{" "}
      {Number(reviewRecords || 0).toLocaleString()} 需复核 +{" "}
      {Number(excludedRecords || 0).toLocaleString()} 已忽略 +{" "}
      {Number(unusableRecords || 0).toLocaleString()} 不可用
      {accountedRecords !== totalRecords &&
        `；仍有 ${Math.abs(totalRecords - accountedRecords).toLocaleString()} 条未对齐`}
    </p>
  );
}
