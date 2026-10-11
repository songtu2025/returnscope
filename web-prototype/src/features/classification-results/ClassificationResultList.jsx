import { ChartBar, Sparkle } from "@phosphor-icons/react";
import { PageHeading } from "../../components/SharedUi";
import { DashboardSelectionBar } from "./ClassificationResultListParts";
import { useResultPoolWorkspace } from "./useResultPoolWorkspace";
import { ResultPoolFilters } from "./ResultPoolFilters";
import { ResultPoolContent } from "./ResultPoolContent";

/** @param {import("./classificationResultListContracts").ClassificationResultListProps} props */
export function ClassificationResultList(props) {
  const state = useResultPoolWorkspace(props);
  const context = { ...props, ...state };
  const {
    route,
    isVersionCreation,
    selectedResults,
    clearSelection,
    continueToDashboard,
    continueToInsight,
    hasNewResults,
    load,
  } = context;
  return (
    <div className="standard-page classification-results-page">
      <PageHeading
        title="分类结果池"
        description="查看最新分类结果，在反馈记录中查看证据或人工修正语义。"
        action={
          <div className="result-creation-actions">
            <button
              className="primary-button"
              disabled={!selectedResults.length}
              title={selectedResults.length ? "" : "请先勾选分类结果"}
              onClick={continueToDashboard}
            >
              <ChartBar size={18} />{" "}
              {isVersionCreation ? "创建看板新版本" : "新建分析看板"}
            </button>
            {!isVersionCreation && (
              <button
                className="secondary-button"
                disabled={!selectedResults.length}
                title={selectedResults.length ? "" : "请先勾选分类结果"}
                onClick={continueToInsight}
              >
                <Sparkle size={18} /> 生成 AI 洞察
              </button>
            )}
          </div>
        }
      />

      {route.selectionToken && (
        <div className="dashboard-selection-notice" role="status">
          <div>
            <b>
              {isVersionCreation
                ? "正在为现有看板选择新版本数据"
                : "当前勾选结果可用于分析看板或 AI 洞察"}
            </b>
            <span>默认仅纳入可用记录，统计范围可在确认时调整。</span>
          </div>
          <button className="text-button" onClick={() => clearSelection(true)}>
            取消选择
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
      {selectedResults.length > 0 && (
        <DashboardSelectionBar
          selected={selectedResults}
          onClear={() => clearSelection()}
        />
      )}
    </div>
  );
}
