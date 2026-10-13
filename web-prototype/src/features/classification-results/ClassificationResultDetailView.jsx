import { useSWRConfig } from "swr";
import { refreshServerState } from "../../shared/serverState";
import { ArrowLeft, ListChecks, WarningCircle } from "@phosphor-icons/react";
import { ResultVersionReviewPanel } from "../review-batches/ResultVersionReviewPanel";
import { EvidenceDrawer } from "./EvidenceDrawer";
import { resultDetailPresentation } from "./resultDetailPresentation";
import { resultDetailActions } from "./resultDetailActions";
import { ResultDetailHeader } from "./ResultDetailHeader";
import { ResultDetailMetrics } from "./ResultDetailMetrics";
import { ResultDetailDrilldown } from "./ResultDetailDrilldown";
import { ResultDetailRecords } from "./ResultDetailRecords";
import { ResultError } from "./ClassificationResultCommon";

/** @typedef {import("./classificationResultDetailContracts").ResultDetailViewProps} ResultDetailViewProps */

/** @param {ResultDetailViewProps} props */
export function ClassificationResultDetailView(props) {
  const { mutate } = useSWRConfig();
  const presentation = resultDetailPresentation(props);
  const actions = resultDetailActions(props);
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
        className="text-button result-back-button page-loading-navigation"
        onClick={() =>
          updateRoute({
            version: "",
            tab: "records",
            recordPage: 1,
            problem: "",
            productName: "",
            productSku: "",
            orderId: "",
            recordQualityStatus: "",
            commentStatus: "",
            systemRerunRequired: "",
          })
        }
      >
        <ArrowLeft size={17} /> 返回分类结果池
      </button>

      <ResultDetailHeader {...context} />

      {props.error && (
        <ResultError message={props.error} onRetry={props.retry} hasData />
      )}

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
            条均需复核，可在查看证据时人工修正。
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
          修改历史
        </button>
      </nav>

      {route.tab === "history" ? (
        <ResultVersionReviewPanel result={result} onSelectVersion={selectVersion} />
      ) : (
        <>
          <ResultDetailMetrics {...context} />

          <ResultDetailDrilldown {...context} />

          <ResultDetailRecords {...context} />

          {selectedGroup && (
            <EvidenceDrawer
              group={selectedGroup}
              disabled={Boolean(result.deleted_at)}
              analysisContext={result.analysis_context}
              onClose={closeEvidence}
              onSaved={(version) => {
                closeEvidence();
                const filtered =
                  route.recordQualityStatus === "review_required" ||
                  route.recordQualityStatus === "unusable" ||
                  route.recordQualityStatus === "excluded" ||
                  route.systemRerunRequired === "true";
                notify(
                  filtered
                    ? "人工修正已保存，无需重跑；记录可能已移出当前筛选。"
                    : "人工修正已保存，无需重跑",
                );
                updateRoute({ version });
                void refreshServerState(mutate, [
                  "classification-results",
                  "analysis-dashboards",
                  "analysis-tasks",
                  "workbench",
                ]).catch(() =>
                  notify("人工修正已保存，部分关联数据更新失败，可重试", "error"),
                );
              }}
              returnFocusRef={evidenceTriggerRef}
            />
          )}
        </>
      )}
    </div>
  );
}
