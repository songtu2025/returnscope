import { ChartBar, Sparkle } from "@phosphor-icons/react";
import { PageHeading } from "../../components/SharedUi";
import { DashboardSelectionBar } from "./ClassificationResultListParts";
import { useResultPoolWorkspace } from "./useResultPoolWorkspace";
import { ResultPoolFilters } from "./ResultPoolFilters";
import { ResultPoolContent } from "./ResultPoolContent";
import { useListReturnPosition } from "../../hooks/useListReturnPosition";
import { classificationResultPoolQuery } from "./classificationResultRoute";

/** @param {import("./classificationResultListContracts").ClassificationResultListProps} props */
export function ClassificationResultList(props) {
  const state = useResultPoolWorkspace(props);
  const { containerRef, titleRef, remember } = useListReturnPosition({
    identity: JSON.stringify(classificationResultPoolQuery(props.route)),
    ready: !state.loading && Boolean(state.data || state.error),
    snapshotRef: props.returnPosition,
  });
  const context = { ...props, ...state, rememberPosition: remember };
  const {
    route,
    selectedResults,
    clearSelection,
    continueToDashboard,
    continueToInsight,
  } = context;
  return (
    <div className="standard-page classification-results-page" ref={containerRef}>
      <PageHeading
        title="分类结果池"
        titleRef={titleRef}
        action={
          <div className="result-creation-actions">
            <button
              className="primary-button"
              disabled={!selectedResults.length}
              title={selectedResults.length ? "" : "请先勾选分类结果"}
              onClick={continueToDashboard}
            >
              <ChartBar size={18} /> 新建分析看板
            </button>
            <button
              className="secondary-button"
              disabled={!selectedResults.length}
              title={selectedResults.length ? "" : "请先勾选分类结果"}
              onClick={continueToInsight}
            >
              <Sparkle size={18} /> 生成 AI 洞察
            </button>
          </div>
        }
      />

      <ResultPoolFilters {...context} />
      <div className="result-detail-tabs" role="group" aria-label="分类结果状态">
        <button
          className={route.lifecycle !== "deleted" ? "active" : ""}
          onClick={() => {
            clearSelection();
            props.updateRoute({ lifecycle: "", page: 1 });
          }}
        >
          当前结果
        </button>
        <button
          className={route.lifecycle === "deleted" ? "active" : ""}
          onClick={() => {
            clearSelection();
            props.updateRoute({ lifecycle: "deleted", page: 1 });
          }}
        >
          已删除
        </button>
      </div>

      <ResultPoolContent {...context} />
      {selectedResults.length > 0 && (
        <DashboardSelectionBar
          selected={selectedResults}
          currentPageIds={
            new Set((context.data?.items ?? []).map((item) => item.version_id))
          }
          loading={context.loading}
          onRemove={context.removeSelection}
          onClear={() => clearSelection()}
        />
      )}
    </div>
  );
}
