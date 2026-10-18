import { useSWRConfig } from "swr";
import { useContext, useEffect, useRef } from "react";
import { PageLoadingContext } from "../../hooks/usePageLoading";
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
import {
  classificationResultReturnLabel,
  returnFromClassificationResult,
} from "./classificationResultRoute";

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
    evidenceNavigation,
    evidenceTriggerRef,
    reviewRecords,
    policy,
    allNeedReviewWithoutProblems,
    selectVersion,
  } = context;
  const loadingScope = useContext(PageLoadingContext);
  const locateRecords = useRef(
    Boolean(route.recordQualityStatus || route.systemRerunRequired),
  );
  useEffect(() => {
    if (
      !locateRecords.current ||
      loadingScope?.initial ||
      props.recordsLoading ||
      props.recordsError ||
      !props.records ||
      route.tab !== "records" ||
      selectedGroup
    )
      return;
    const region = document.getElementById("classification-order-records");
    if (!region) return;
    region.scrollIntoView({ block: "start" });
    region.focus({ preventScroll: true });
    locateRecords.current = false;
  }, [
    loadingScope?.initial,
    props.recordsLoading,
    props.recordsError,
    props.records,
    route.tab,
    selectedGroup,
  ]);
  const refreshRelated = async () => {
    await refreshServerState(mutate, [
      "classification-results",
      "analysis-dashboards",
      "analysis-tasks",
      "workbench",
    ]).catch(() => notify("人工修正已保存，部分关联数据更新失败，可重试", "error"));
  };
  return (
    <div className="standard-page classification-results-page result-detail-page">
      <button
        className="text-button result-back-button page-loading-navigation"
        onClick={() => returnFromClassificationResult(route, updateRoute)}
      >
        <ArrowLeft size={17} /> {classificationResultReturnLabel(route)}
      </button>

      <ResultDetailHeader {...context} />

      {route.dashboardReturn && (
        <p role="status">
          当前展示看板来源结果 v{result.version}，返回可继续查看原看板。
        </p>
      )}

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
          {route.tab === "history" && !route.dashboardReturn
            ? "返回最新分类数据"
            : "分类数据"}
        </button>
        <button
          className={route.tab === "history" ? "active" : ""}
          onClick={() => updateRoute({ tab: "history" })}
        >
          修改历史
        </button>
      </nav>

      {route.tab === "history" ? (
        <ResultVersionReviewPanel
          result={result}
          onSelectVersion={selectVersion}
          pinnedVersion={Boolean(route.dashboardReturn)}
        />
      ) : (
        <>
          <ResultDetailMetrics {...context} />

          <ResultDetailDrilldown {...context} />

          <ResultDetailRecords {...context} />

          {selectedGroup && (
            <EvidenceDrawer
              group={selectedGroup}
              navigation={evidenceNavigation}
              disabled={Boolean(result.deleted_at)}
              analysisContext={result.analysis_context}
              onClose={closeEvidence}
              onSavedBeforeExit={refreshRelated}
              onSaved={async (version, advance) => {
                await evidenceNavigation.saved(version, advance);
                void refreshRelated();
              }}
              returnFocusRef={evidenceTriggerRef}
            />
          )}
        </>
      )}
    </div>
  );
}
