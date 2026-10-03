import { ResultPoolInsightDialog } from "./ResultPoolInsightDialog";
import { ChartBar } from "@phosphor-icons/react";
import { PageHeading } from "../../components/SharedUi";
import { DashboardSelectionBar } from "./ClassificationResultListParts";
import { ResultWorkspaceNav } from "./ResultWorkspaceNav";
import { useResultPoolWorkspace } from "./useResultPoolWorkspace";
import { ResultPoolFilters } from "./ResultPoolFilters";
import { ResultPoolContent } from "./ResultPoolContent";

/** @param {import("./classificationResultListContracts").ClassificationResultListProps} props */
export function ClassificationResultList(props) {
  const state = useResultPoolWorkspace(props);
  const context = { ...props, ...state };
  const {
    route,
    updateRoute,
    selectionIntent,
    selectedResults,
    startSelection,
    clearSelection,
    continueToDashboard,
    insightOpen,
    hasNewResults,
    load,
  } = context;
  return (
    <div className="standard-page classification-results-page">
      <ResultWorkspaceNav
        active={route.qualityStatus === "review_required" ? "pending" : "results"}
      />
      <PageHeading
        eyebrow="不可变分类数据资产"
        title="分类结果池"
        description="每个已完成 Listing 独立发布结果版本，可在网页查看订单级分类与证据。"
        action={
          <button className="primary-button" onClick={startSelection}>
            <ChartBar size={18} /> 新建分析看板
          </button>
        }
      />

      {route.selectionToken && selectionIntent === "dashboard" && (
        <div className="dashboard-selection-notice" role="status">
          <div>
            <b>正在选择看板数据</b>
            <span>“需复核”版本也可加入；看板会自动排除待复核和已排除记录。</span>
          </div>
          <button
            className="text-button"
            onClick={() => updateRoute({ selectionToken: "" })}
          >
            退出选择
          </button>
        </div>
      )}

      {hasNewResults && (
        <div className="result-refresh-banner" role="status">
          <span>有新的 Listing 分类结果可用，当前列表未自动改变。</span>
          <button className="secondary-button" onClick={load}>
            刷新列表
          </button>
        </div>
      )}

      <ResultPoolFilters {...context} />

      <ResultPoolContent {...context} />
      {route.selectionToken && selectionIntent === "dashboard" && (
        <DashboardSelectionBar
          selected={selectedResults}
          onClear={clearSelection}
          onContinue={continueToDashboard}
        />
      )}
      {insightOpen && <ResultPoolInsightDialog {...context} />}
    </div>
  );
}
